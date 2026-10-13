#!/usr/bin/env python3
"""pipeline: batched build + parallel Comparator checks for OpenAI/math, with per-batch C archiving.

Purpose: the one-config-at-a-time driver (overnight.sh) left most of the 16 cores idle: Lake builds are wide only
early, and Comparator checks are single-threaded. This builds a BATCH of configs' modules in one `lake build` (all cores,
shared dependencies compiled once) while up to W checks run in parallel. A batch's checks are submitted as soon as its build
ends and the next build starts at once, so one slow check never holds up the builds behind it; a batch's generated C files are
archived (compress, verify, remove) when all of its checks have finished (at most --max-pending batches are in that state). Concurrency of builds + checks in one Lake workspace was tested
(scratch/conc: 3 checks + a build + a big check, no interference).

Resumable via results/cmp-all/all.jsonl (accepted configs skipped). Pause/resume instantly with tools/pause.sh and tools/resume.sh (SIGSTOP/SIGCONT; no STOP file). Writes results/cmp-all/ALERT and exits if disk cannot be kept above MIN_GIB.
Usage: pipeline.py [--workers 3] [--cap-modules 2500] [--max-configs 12]   (env PATH must include landrun, lean4export, nanoda_bin, elan)
"""
import os, sys, re, json, glob, time, signal, subprocess, shutil, argparse, datetime, concurrent.futures as cf

base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
root = base + '/src/lean'; R = base + '/results/cmp-all'; bld = root + '/.lake/build'
ap = argparse.ArgumentParser(); ap.add_argument('--workers', type=int, default=2)
ap.add_argument('--cap-modules', type=int, default=2500); ap.add_argument('--max-configs', type=int, default=12)
ap.add_argument('--min-gib', type=int, default=25); ap.add_argument('--max-pending', type=int, default=2, help='most batches whose checks may still be running before the next build waits'); ap.add_argument('--order', default=base + '/results/config-order.json')
ap.add_argument('--results', default=base + '/results/cmp-all')
ap.add_argument('--lean-slots', type=int, default=6, help='max concurrent Lean compiles (via the throttled toolchain in ext/sysroot-throttled)')
ap.add_argument('--build-cpus', default='6-15', help='CPU list the build may use (taskset); limits how many compiles run at once')
ap.add_argument('--start-avail-gib', type=float, default=20, help='wait for this much available memory before starting a batch build')
ap.add_argument('--psi-pause', type=float, default=25, help='freeze the build when memory pressure (some avg10, %%) exceeds this')
ap.add_argument('--psi-resume', type=float, default=8); ap.add_argument('--min-avail-gib', type=float, default=3)
ap.add_argument('--resume-avail-gib', type=float, default=4.5); a = ap.parse_args()
R = a.results
imp = re.compile(rb"^\s*(?:public\s+|meta\s+)*import\s+(?:public\s+|meta\s+)*(\S+)", re.M)
def log(m):
    line = f"{datetime.datetime.now().astimezone().isoformat(timespec='seconds')} pipeline: {m}"
    open(R + '/driver.log', 'a').write(line + "\n"); print(line, flush=True)       # also visible in the tmux window
free_gib = lambda: shutil.disk_usage('/home').free / 2**30


def notify(msg):
    """Make a disk/stall problem visible: ALERT file, log, terminal bell, tmux message, desktop notification if available."""
    open(R + '/ALERT', 'a').write(f"{datetime.datetime.now().astimezone().isoformat(timespec='seconds')} {msg}\n")
    log('ALERT ' + msg)
    print('\a', end='', flush=True)
    stamped = time.strftime('%H:%M:%S') + ' ' + msg          # desktop notifications can sit queued for hours: show when it was raised
    for cmd in (['tmux', 'display-message', '-d', '0', 'ALERT: ' + stamped], ['notify-send', 'Comparator pipeline ' + time.strftime('%H:%M:%S'), msg]):
        try: subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except Exception: pass


def cfg(name): return json.load(open(f'{root}/ComparatorChallenges/{name}.json'))


def closure(mods):
    seen, todo = set(), list(mods)
    while todo:
        m = todo.pop(); p = os.path.join(root, *m.split('.')) + '.lean'
        if m in seen or not os.path.exists(p): continue
        seen.add(m); todo += [x.decode() for x in imp.findall(open(p, 'rb').read())]
    return seen


def ir_files(mods):
    out = []
    for m in mods:
        st = 'ir/' + '/'.join(m.split('.'))
        out += [st + '.c', st + '.c.hash', st + '.setup.json']
    return out


def restore(files):
    missing = [f for f in files if not os.path.exists(f'{bld}/{f}')]
    if not missing: return 0
    lst = f'{R}/restore.lst'; open(lst, 'w').write('\n'.join(missing) + '\n')
    for arch in sorted(glob.glob(base + '/archive/*.tar.zst')):
        subprocess.run(['tar', '--zstd', '-xf', arch, '-C', bld, '--files-from', lst, '--ignore-failed-read'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return sum(os.path.exists(f'{bld}/{f}') for f in missing)


def archive(name, files):
    have = [f for f in files if os.path.exists(f'{bld}/{f}')]
    if not have: return
    lst = f'{R}/archive.lst'; open(lst, 'w').write('\n'.join(have) + '\n')
    out = f'{base}/archive/{name}.tar.zst'; os.makedirs(base + '/archive', exist_ok=True)
    p = subprocess.run(f"nice -n 10 tar -C {bld} -cf - --files-from {lst} | zstd -T4 -3 -q -o {out}", shell=True)
    t = subprocess.run(['zstd', '-tq', out])
    if p.returncode == 0 and t.returncode == 0:
        for f in have: os.remove(f'{bld}/{f}')
        log(f"archived {name}: {len(have)} files, {os.path.getsize(out)/2**20:.0f} MiB")
    else:
        log(f"ARCHIVE FAILED {name}; originals kept")


def accepted():
    s = set()
    if os.path.exists(R + '/all.jsonl'):
        for l in open(R + '/all.jsonl'):
            d = json.loads(l)
            if d.get('outcome') == 'accepted': s.add(d['config'])
    return s


def make_batches():
    order = json.load(open(a.order))
    size = {n: sz for sz, n, s in json.load(open(base + '/results/config-solution-size.json'))}
    inflight = {n for n in order if subprocess.run(['pgrep', '-f', f'bin/comparator ComparatorChallenges/{n}.json'], capture_output=True).returncode == 0}
    if inflight: log(f"skipping configs whose check is already running elsewhere: {sorted(inflight)} (tools/recover_records.py adds their results)")
    todo = [n for n in order if n not in accepted() and n not in inflight]
    batches, cur, tot = [], [], 0
    for n in todo:
        sz = size[n]
        if cur and (tot + sz > a.cap_modules or len(cur) >= a.max_configs):
            batches.append(cur); cur, tot = [], 0
        cur.append(n); tot += sz
        if sz > a.cap_modules: batches.append(cur); cur, tot = [], 0
    if cur: batches.append(cur)
    return batches


def check(name, bid):
    env = dict(os.environ, SKIP_BUILD='1', BATCH_ID=str(bid))
    subprocess.run(['python3', '-I', base + '/tools/run_comparator_batch.py', root, R + '/all.jsonl', name], env=env,
                   stdout=open(R + '/driver.log', 'a'), stderr=subprocess.STDOUT)


def mem_avail_gib():
    for l in open('/proc/meminfo'):
        if l.startswith('MemAvailable:'): return int(l.split()[1]) / 2**20


def mem_psi_some10():
    return float(open('/proc/pressure/memory').readline().split('avg10=')[1].split()[0])


def valve_decision(paused, calm, psi, avail):
    """Pure decision rule for the memory valve. Returns (action, new_calm): action is 'pause', 'resume' or None.
    Pause when pressure is high or available memory is tiny; resume only after 3 consecutive calm samples."""
    if not paused:
        return ('pause', 0) if (psi > a.psi_pause or avail < a.min_avail_gib) else (None, 0)
    calm = calm + 1 if (psi < a.psi_resume and avail > a.resume_avail_gib) else 0
    return ('resume', 0) if calm >= 3 else (None, calm)


def descendants(pid):
    out = [pid]
    for c in subprocess.run(['pgrep', '-P', str(pid)], capture_output=True, text=True).stdout.split():
        out += descendants(int(c))
    return out


class MemoryValve:
    """Backstop: systemd-oomd kills a whole cgroup when user-session memory pressure stays above 50% for 20 s. This freezes the
    build tree (SIGSTOP) as soon as pressure passes psi-pause or available memory is tiny, and thaws it after pressure subsides,
    so the machine never reaches the kill threshold. Frozen processes keep their memory but stop allocating and stalling."""
    def __init__(self, root): self.root, self.paused, self.calm, self.since, self.noted = root, [], 0, 0, 0
    def step(self):
        psi, av = mem_psi_some10(), mem_avail_gib()
        act, self.calm = valve_decision(bool(self.paused), self.calm, psi, av)
        if act == 'pause':
            self.paused = descendants(self.root); self.since = self.noted = time.time()
            for _ in range(2):
                for q in descendants(self.root):
                    try: os.kill(q, signal.SIGSTOP)
                    except OSError: pass
                time.sleep(0.3)
            log(f"memory valve: froze build ({len(self.paused)} processes) at pressure {psi:.0f}% and {av:.1f} GiB available")
        elif act == 'resume':
            for q in sorted(descendants(self.root), reverse=True):
                try: os.kill(q, signal.SIGCONT)
                except OSError: pass
            log(f"memory valve: thawed build after {time.time() - self.since:.0f} s (pressure {psi:.0f}%, {av:.1f} GiB available)")
            self.paused = []
        elif self.paused and time.time() - self.noted > 600:
            self.noted = time.time(); notify(f'build frozen {time.time() - self.since:.0f} s by the memory valve; {av:.1f} GiB available, pressure {psi:.0f}%')
    def release(self):
        if self.paused:
            for q in descendants(self.root):
                try: os.kill(q, signal.SIGCONT)
                except OSError: pass


def wait_for_memory():
    waited = 0
    while mem_avail_gib() < a.start_avail_gib:
        if waited % 300 == 0: log(f"waiting for memory: {mem_avail_gib():.1f} GiB available, need {a.start_avail_gib:.0f}")
        if waited and waited % 1800 == 0: notify(f'pipeline waiting {waited // 60} min for {a.start_avail_gib:.0f} GiB of available memory')
        time.sleep(30); waited += 30


def build(bid, names):
    mods = sorted({m for n in names for m in (cfg(n)['solution_module'], cfg(n)['challenge_module'])})
    mon = f'{R}/logs/batch{bid}.buildmon'; t = time.time()
    wait_for_memory()
    proc = subprocess.Popen(['python3', '-I', base + '/tools/vmamon.py', '--out', mon, '--interval', '0.5', '--label', f'batch{bid}-build', '--',
                             'taskset', '-c', a.build_cpus, base + '/ext/sysroot-throttled/bin/lake', 'build'] + mods, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            env=dict(os.environ, LEAN_SYSROOT=base + '/ext/sysroot-throttled', LEAN_SLOTS=str(a.lean_slots)))
    valve = MemoryValve(proc.pid)
    while proc.poll() is None:
        try: valve.step()
        except Exception as e: log(f'valve error: {type(e).__name__}: {e}')
        time.sleep(2)
    valve.release()
    rec = dict(batch=bid, configs=names, build_wall_s=round(time.time() - t, 1), free_gib_after=round(free_gib(), 1))
    try:
        s = json.load(open(mon + '/summary.json')); txt = open(mon + '/stdout.log', errors='replace').read()
        times = sorted([(float(x), m) for m, x in re.findall(r"Built (\S+) \(([\d.]+)s\)", txt)], reverse=True)
        rec.update(exit=s['exit_code'], peak_vmas=s['peak_per_process_vmas_sampled'], peak_procs=s['peak_concurrent_processes'],
                   vmamon_class=s['classification'], modules_built=len(times), slowest=[dict(module=m, s=x) for x, m in times[:3]])
    except Exception as e: rec['monitor_error'] = str(e)[:100]
    open(R + '/batches.jsonl', 'a').write(json.dumps(rec) + '\n')
    return rec


os.makedirs(R + '/logs', exist_ok=True)
# startup sweep: archive generated C left on disk by already-accepted configs (e.g. restored for an earlier run)
_acc = sorted(accepted())
if _acc:
    _mods = closure([m for n in _acc for m in (cfg(n)['solution_module'], cfg(n)['challenge_module'])])
    archive(f'startup-{int(time.time())}', ir_files(_mods))
batches = make_batches(); log(f"{len(batches)} batches, workers={a.workers}, cap={a.cap_modules}")
pool = cf.ThreadPoolExecutor(a.workers)


pending = []          # [(futures, files, bid)] for batches whose checks were submitted but whose generated C is not yet archived


def reap(keep=(), block_oldest=False):
    """Archive every pending batch whose checks have all finished. A file still needed by another pending batch, or listed in keep
    (the batch about to build), stays on disk. With block_oldest, first wait for the oldest pending batch's checks to finish."""
    if block_oldest and pending:
        for f in pending[0][0]: f.result()
    for entry in list(pending):
        if not all(f.done() for f in entry[0]): continue
        for f in entry[0]: f.result()
        others = set(keep).union(*[set(e[1]) for e in pending if e is not entry])
        archive(f'batch{entry[2]}-{int(time.time())}', [f for f in entry[1] if f not in others])
        pending.remove(entry)


RUN = time.strftime('%m%d%H%M')      # batch ids are unique across restarts: <run start>-<index>
for bi, names in enumerate(batches):
    bid = f'{RUN}-{bi}'
    mods = closure([m for n in names for m in (cfg(n)['solution_module'], cfg(n)['challenge_module'])])
    files = ir_files(mods); est = len(mods) * 0.0065
    reap(keep=files)                                                     # free what finished checks no longer need
    if len(pending) >= a.max_pending: log(f'{len(pending)} batches still being checked; waiting for the oldest before building batch {bid}'); reap(keep=files, block_oldest=True)
    waited = 0
    while free_gib() < a.min_gib + est:                                  # wait (do not exit) until space appears: finished checks free their batch, or the user frees some
        reap(keep=files)
        if free_gib() >= a.min_gib + est: break
        if waited % 1800 == 0: notify(f'disk {free_gib():.0f}G free, batch {bid} needs ~{est+a.min_gib:.0f}G; waiting for checks to finish or free space')
        time.sleep(60); waited += 60
    if waited and os.path.exists(R + '/ALERT') and free_gib() >= a.min_gib + est:
        os.rename(R + '/ALERT', R + f'/ALERT.resolved.{int(time.time())}'); log('disk recovered; ALERT cleared')
    log(f"batch {bid}: {len(names)} configs {names[:4]}... modules~{len(mods)} free={free_gib():.0f}G restored={restore(files)} checks_pending={len(pending)}")
    rec = build(bid, names)
    log(f"batch {bid}: build exit={rec.get('exit')} {rec.get('build_wall_s')}s built={rec.get('modules_built')} peak_vmas={rec.get('peak_vmas')}")
    pending.append(([pool.submit(check, n, bid) for n in names], files, bid))   # checks start now; the next build does not wait for them
    reap(keep=files)
while pending: reap(block_oldest=True)
log('pipeline finished or stopped')
