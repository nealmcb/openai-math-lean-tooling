#!/usr/bin/env python3
"""nanoda_ab: run several nanoda builds on the same Comparator configurations, exporting each solution once, and record every run.

Purpose: compare nanoda builds (for example upstream master before and after a pull request, nanoda_lib PR 59) on correctness and cost on the same machine: whether anything that passed
now fails, whether the 15 configurations that failed with the pinned build pass, and how wall time, CPU time and peak memory change. For each configuration it exports the solution once
with lean4export (the same targets as Comparator and tools/nanoda_retest.py), runs every build on that export in the order given, deletes the export, and appends one JSON line per
(configuration, build) to the output file: label, commit of the build's source tree, export size and seconds, threads, exit code, wall and CPU seconds, peak RSS and the last output
lines. Each stage runs in a transient systemd unit with a memory cap, no swap and a runtime limit. Configurations run JOBS at a time, in the order given (put the largest first).
Needs the closure of every solution built under src/lean (restore it from the Lake cache with tools/restore_ir_for.py --from-cache, or use a machine with the full build).
--stop-on-regression compares every later build with the first one (the baseline) and, at the first configuration where a later build fails although the baseline passed, or takes more
than twice the baseline's wall time and over 60 s, or more than twice its peak memory and over 4 GiB, writes a line with "regression" to the output and starts no further configuration
(those already running finish). A run in which systemd-run itself fails ("Failed to connect to bus", as when a spot instance is being reclaimed) is not a result: it is not
recorded, no further configuration starts, and the exit code is 3. --resume skips the configurations that already have a record for every build in the output file (a run interrupted by a spot reclaim
loses only the configurations in flight), and refuses to continue if the file already holds a "regression" line. Each record carries the sha256 of the build's binary and a "host" entry (EC2 instance id, type, lifecycle and zone, CPU model, threads per core, memory, boot id);
`--print-host` prints that entry as one JSON line and exits. --base DIR overrides the checkout whose src/lean, ext/ and scratch/ are used (default: the checkout this script is in).
Scheduling: a CONFIG may carry its own settings as NAME:THREADS:MEM:TIMEOUT (for example SKRatio:8:60G:7200), the defaults being --threads, --mem and --timeout. --jobs is the most
configurations running at once; --cpus N and --mem-budget GIB add a budget (the sum of the running configurations' threads, and of their memory caps) that a new one must fit in.
Configurations start in the order given, but one that does not fit yet lets later ones start in the free cores and memory, so put the largest first and the small ones fill in
around them as the big ones finish.
Usage: nanoda_ab.py --build LABEL=PATH [--build LABEL=PATH ...] [--jobs 4] [--threads 4] [--mem 30G] [--timeout 3600] [--cpus N] [--mem-budget GIB] [--out results/nanoda-ab.jsonl] [--base DIR] [--stop-on-regression] [--resume] CONFIG [CONFIG ...]
       (CONFIG may also be @FILE, one configuration per line)
"""
import os, sys, json, time, subprocess, datetime, threading
from concurrent.futures import ThreadPoolExecutor
base = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')); root = base + '/src/lean'
builds, names, opt, i, a = [], [], {'--jobs': '4', '--threads': '4', '--mem': '30G', '--timeout': '3600', '--out': base + '/results/nanoda-ab.jsonl', '--base': None, '--cpus': '0', '--mem-budget': '0'}, 0, sys.argv[1:]
stop_on_regression = '--stop-on-regression' in a; resume = '--resume' in a; a = [x for x in a if x not in ('--stop-on-regression', '--resume')]
while i < len(a):
    if a[i] == '--build': label, path = a[i + 1].split('=', 1); builds.append((label, os.path.abspath(path))); i += 2
    elif a[i] in opt: opt[a[i]] = a[i + 1]; i += 2
    elif a[i].startswith('@'): names += [l.strip() for l in open(a[i][1:]) if l.strip()]; i += 1
    else: names.append(a[i]); i += 1
def parse_spec(s):   # NAME or NAME:THREADS:MEM:TIMEOUT
    f = s.split(':'); return dict(name=f[0], threads=int(f[1]) if len(f) > 1 else int(opt['--threads']), mem=f[2] if len(f) > 2 else opt['--mem'], timeout=f[3] if len(f) > 3 else opt['--timeout'])
specs = [parse_spec(s) for s in names]
if opt['--base']: base = os.path.abspath(opt['--base']); root = base + '/src/lean'
QUOT = ['Quot', 'Quot.mk', 'Quot.lift', 'Quot.ind']
PRIM = ['Nat.add', 'Nat.sub', 'Nat.mul', 'Nat.pow', 'Nat.gcd', 'Nat.div', 'Nat.mod', 'Nat.beq', 'Nat.ble', 'Nat.land', 'Nat.lor', 'Nat.xor', 'Nat.shiftLeft',
        'Nat.shiftRight', 'String.ofList', 'Char.ofNat', 'List', 'eagerReduce', 'Nat', 'String', 'String.mk', 'Char', 'optParam', 'autoParam', 'semiOutParam', 'outParam']
env_path = f"{base}/ext/lean4export/.lake/build/bin:{os.path.expanduser('~')}/.elan/bin:{os.environ['PATH']}"
W = base + '/scratch/ab'; os.makedirs(W, exist_ok=True); lock = threading.Lock()
def commit_of(binpath):
    d = binpath
    for _ in range(4):
        d = os.path.dirname(d)
        if os.path.exists(os.path.join(d, 'Cargo.toml')):
            return subprocess.run(['git', '-C', d, 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip() or None
    return None
def host_info():
    """The machine this runs on: on EC2 the instance id, type, lifecycle (spot or on-demand) and zone from the metadata service, everywhere the CPU model, thread layout and boot id."""
    import urllib.request, socket
    h = dict(hostname=socket.gethostname(), cpus=os.cpu_count())
    try:
        cpu = [l.split(':', 1)[1].strip() for l in open('/proc/cpuinfo') if l.startswith('model name')]; h['cpu_model'] = cpu[0] if cpu else None
        lscpu = subprocess.run(['lscpu'], capture_output=True, text=True).stdout
        h['threads_per_core'] = next((int(l.split(':')[1]) for l in lscpu.splitlines() if l.startswith('Thread(s) per core')), None)
        h['mem_gib'] = round(int(next(l for l in open('/proc/meminfo') if l.startswith('MemTotal')).split()[1]) / 2**20)
        h['boot_id'] = open('/proc/sys/kernel/random/boot_id').read().strip()
        tok = urllib.request.urlopen(urllib.request.Request('http://169.254.169.254/latest/api/token', method='PUT', headers={'X-aws-ec2-metadata-token-ttl-seconds': '60'}), timeout=2).read().decode()
        for k, path in (('instance_id', 'instance-id'), ('instance_type', 'instance-type'), ('lifecycle', 'instance-life-cycle'), ('zone', 'placement/availability-zone')):
            h[k] = urllib.request.urlopen(urllib.request.Request('http://169.254.169.254/latest/meta-data/' + path, headers={'X-aws-ec2-metadata-token': tok}), timeout=2).read().decode()
    except Exception: pass
    return h
if '--print-host' in sys.argv: print(json.dumps(dict(host=host_info(), at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')))); sys.exit(0)
HOST = host_info()
commits = {label: commit_of(path) for label, path in builds}
import hashlib
shas = {label: hashlib.sha256(open(path, 'rb').read()).hexdigest() for label, path in builds}
if resume and os.path.exists(opt['--out']):
    done = {}
    for l in open(opt['--out']):
        r = json.loads(l)
        if r.get('regression'): sys.exit(f"{opt['--out']} holds a regression ({r['regression']}); not continuing")
        if r.get('label') and 'rc' in r: done.setdefault(r['config'], set()).add(r['label'])
    specs = [s for s in specs if done.get(s['name'], set()) != {label for label, _ in builds}]
    print(f'resuming: {len(done)} configurations already recorded, {len(specs)} to go', flush=True)
def stage(cmd, mem, timeout):
    full = ['systemd-run', '--user', '--wait', '--pipe', '--collect', '-p', f"MemoryMax={mem}", '-p', 'MemorySwapMax=0', '-p', f"RuntimeMaxSec={timeout}", '-E', f'PATH={env_path}',
            '/usr/bin/time', '-f', 'TIME %e %U %S %M', *cmd]
    t = time.time(); p = subprocess.run(full, capture_output=True, text=True); wall = time.time() - t
    tl = [l for l in p.stderr.splitlines() if l.startswith('TIME ')]
    cpu, rss = (float(tl[-1].split()[2]) + float(tl[-1].split()[3]), int(tl[-1].split()[4]) / 2**20) if tl else (None, None)
    return p, wall, cpu, rss
def record(rec):
    with lock:
        open(opt['--out'], 'a').write(json.dumps(rec) + '\n')
        print(json.dumps({k: rec.get(k) for k in ('config', 'label', 'export_bytes', 'rc', 'wall_s', 'rss_gib')}), flush=True)
stop = threading.Event(); infra_failed = threading.Event(); export_failures = []
def regression(runs):
    (b_label, _), *others = builds; b = runs.get(b_label)   # the first build is the baseline
    if not b or b['rc'] != 0: return None
    for label, _ in others:
        r = runs.get(label)
        if not r: continue
        if r['rc'] != 0: return f"{label} fails (rc {r['rc']}) where {b_label} passes"
        if r['wall_s'] > 2 * b['wall_s'] and r['wall_s'] > 60: return f"{label} takes {r['wall_s']} s against {b['wall_s']} s for {b_label}"
        if r['rss_gib'] and b['rss_gib'] and r['rss_gib'] > 2 * b['rss_gib'] and r['rss_gib'] > 4: return f"{label} uses {r['rss_gib']} GiB against {b['rss_gib']} GiB for {b_label}"
    return None
def one(s):
    n, threads, mem, tmo = s['name'], s['threads'], s['mem'], s['timeout']
    if stop.is_set(): return
    c = json.load(open(f'{root}/ComparatorChallenges/{n}.json')); exp = f'{W}/{n}.export'
    targets = QUOT + c['theorem_names'] + c.get('permitted_axioms', []) + PRIM + (c.get('definition_names') or [])
    p, wall, _, _ = stage(['bash', '-c', f'cd {root} && lake env lean4export {c["solution_module"]} -- ' + ' '.join(targets) + f' > {exp}'], mem, tmo)
    size = os.path.getsize(exp) if os.path.exists(exp) else 0
    if p.returncode or not size:
        record(dict(config=n, label=None, export_rc=p.returncode, export_bytes=size, note='export failed: ' + p.stderr.strip()[-200:]))
        with lock:   # three export failures in a row mean the machine, not the configurations, is broken: stop instead of failing the whole list
            export_failures.append(n)
            if len(export_failures) >= 3: stop.set()
        return
    export_failures.clear()
    cfg = f'{W}/{n}.json'
    json.dump(dict(use_stdin=False, export_file_path=exp, permitted_axioms=c.get('permitted_axioms', []), unpermitted_axiom_hard_error=True, num_threads=threads,
                   nat_extension=True, string_extension=True), open(cfg, 'w'))
    runs = {}
    for label, path in builds:
        started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
        p, w, cpu, rss = stage([path, cfg], mem, tmo)
        if 'Failed to connect to bus' in p.stderr + p.stdout:   # systemd-run itself failed (the machine is going down, or has no user manager): not a result of the build
            infra_failed.set(); stop.set(); os.remove(cfg); os.remove(exp); return
        rec = dict(config=n, label=label, commit=commits[label], sha256=shas[label], host=HOST, started=started, threads=threads, mem_cap=mem, timeout_s=int(tmo), export_s=round(wall, 1), export_bytes=size,
                   rc=p.returncode, wall_s=round(w, 1), cpu_s=cpu and round(cpu, 1), rss_gib=rss and round(rss, 2), tail=(p.stdout + p.stderr).strip().splitlines()[-3:])
        record(rec); runs[label] = rec
    why = regression(runs) if stop_on_regression else None
    if why: record(dict(config=n, regression=why)); stop.set()
    os.remove(cfg); os.remove(exp)
gib = lambda m: float(m.rstrip('Gg'))   # memory caps are given like 60G
cpu_budget, mem_budget, max_jobs = int(opt['--cpus']), float(opt['--mem-budget']), int(opt['--jobs'])
used = dict(cpu=0, mem=0.0, jobs=0); cv = threading.Condition(); pending, workers = list(specs), []
def run(s):
    try: one(s)
    finally:
        with cv: used['cpu'] -= s['threads']; used['mem'] -= gib(s['mem']); used['jobs'] -= 1; cv.notify_all()
with cv:   # in list order, but a configuration that does not fit yet lets later, smaller ones start in the free cores and memory
    while pending and not stop.is_set():
        fits = lambda s: used['jobs'] < max_jobs and (not cpu_budget or used['cpu'] + s['threads'] <= cpu_budget) and (not mem_budget or used['mem'] + gib(s['mem']) <= mem_budget)
        pick = next((s for s in pending if fits(s)), pending[0] if used['jobs'] == 0 else None)   # nothing running: start the first even if it exceeds the budget
        if pick is None: cv.wait(timeout=5); continue
        pending.remove(pick); used['cpu'] += pick['threads']; used['mem'] += gib(pick['mem']); used['jobs'] += 1
        workers.append(threading.Thread(target=run, args=(pick,))); workers[-1].start()
for t in workers: t.join()
if infra_failed.is_set(): print('systemd-run failed (no user bus); stopped without recording the interrupted runs', flush=True); sys.exit(3)
