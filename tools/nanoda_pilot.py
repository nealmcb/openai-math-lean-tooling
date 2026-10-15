#!/usr/bin/env python3
"""nanoda_pilot: how much slower or faster is the nanoda kernel than Lean's own kernel on the same solution?

Purpose: Comparator can check a solution with a second, independent kernel (nanoda, written in Rust) in addition to Lean's built-in
one, but only 2 of the 416 configurations enable it, so its cost on this library is unknown. For each chosen configuration this
runs the unchanged Comparator check with `enable_nanoda: true` set in a scratch copy of the configuration (the repository is not
touched), through the same sandboxed systemd unit as run_comparator_batch.py and under tools/vmamon.py, and records the time and
time and peak memory of the nanoda phase (Comparator runs nanoda first, then Lean's kernel, on the same export; vmamon's kernel_timeline
finds nanoda by process name) and the time of the Lean-kernel phase (the rest of the run after nanoda ends, within the comparator process), the export size, and whether both kernels accepted. The ratio nanoda time / Lean kernel time
per configuration, and how it moves with export size, is the result. Requires every module of the configuration's closure to be
built and ext/bin/nanoda_bin on PATH (the tool sets it).
Selection: explicit CONFIG names, or --spread N, which takes N accepted configurations evenly spaced by export size
(results/export-probe.csv) and runs them smallest first, so a stop (--budget-hours, --max-minutes, the STOP file) always leaves the
small and medium sizes measured. A check that runs past --max-minutes is stopped and recorded as "timeout". Memory: a check starts
only if MemAvailable stays above --reserve-gib after --est-gib, and its unit is capped by --memmax. Resumable: configurations
already in results/nanoda-pilot/all.jsonl with outcome accepted or rejected are skipped. --after-unit U waits until the systemd user
unit U is no longer active (for example the root build) before starting.
Usage: nanoda_pilot.py [CONFIG ...] [--spread 12] [--budget-hours 6] [--max-minutes 90] [--memmax 24G] [--reserve-gib 12] [--est-gib 10]
                       [--after-unit root-build] [--rerun] [--dry-run]
"""
import os, sys, re, csv, json, time, argparse, subprocess, datetime
ap = argparse.ArgumentParser(); ap.add_argument('configs', nargs='*')
ap.add_argument('--spread', type=int, default=0); ap.add_argument('--budget-hours', type=float, default=6); ap.add_argument('--max-minutes', type=float, default=90)
ap.add_argument('--memmax', default='24G'); ap.add_argument('--reserve-gib', type=float, default=12); ap.add_argument('--est-gib', type=float, default=10)
ap.add_argument('--after-unit', default=None); ap.add_argument('--rerun', action='store_true', help='run configurations even if all.jsonl already has a record (for example with a larger --memmax)'); ap.add_argument('--dry-run', action='store_true'); a = ap.parse_args()
base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')); root = base + '/src/lean'
R = base + '/results/nanoda-pilot'; S = base + '/scratch/nanoda-pilot'; os.makedirs(R + '/logs', exist_ok=True); os.makedirs(S, exist_ok=True)
imp = re.compile(rb"^\s*(?:public\s+|meta\s+)*import\s+(?:public\s+|meta\s+)*(\S+)", re.M)
t_start = time.time()


def log(m):
    line = f"{datetime.datetime.now().astimezone().isoformat(timespec='seconds')} nanoda_pilot: {m}"
    open(R + '/driver.log', 'a').write(line + '\n'); print(line, flush=True)


def deps(m):
    try: return [x.decode() for x in imp.findall(open(os.path.join(root, *m.split('.')) + '.lean', 'rb').read()) if x.decode().startswith(('OAI', 'ComparatorChallenges'))]
    except OSError: return []


def built(c):
    seen, todo = set(), [c['solution_module'], c['challenge_module']]
    while todo:
        m = todo.pop()
        if m in seen: continue
        seen.add(m); todo += deps(m)
        if not os.path.exists(os.path.join(root, '.lake/build/lib/lean', *m.split('.')) + '.olean'): return False
    return True


def avail_gib():
    for l in open('/proc/meminfo'):
        if l.startswith('MemAvailable:'): return int(l.split()[1]) / 2**20


def tail(path, n=3000):
    with open(path, 'rb') as f:
        f.seek(0, 2); s = f.tell(); f.seek(max(0, s - n)); return f.read().decode(errors='replace')


def choose():
    cfgs = {f[:-5]: json.load(open(f'{root}/ComparatorChallenges/{f}')) for f in sorted(os.listdir(root + '/ComparatorChallenges')) if f.endswith('.json')}
    if a.configs: return [(n, cfgs[n]) for n in a.configs]
    size = {r['config']: int(r['export_bytes']) for r in csv.DictReader(open(base + '/results/export-probe.csv')) if r['exit'] == '0'}
    ok = {n for n, c in cfgs.items() if n in size and not c.get('enable_nanoda') and built(c)}
    ranked = sorted(ok, key=lambda n: size[n])
    k = max(1, a.spread); picks = [ranked[round(i * (len(ranked) - 1) / max(1, k - 1))] for i in range(k)] if k > 1 else ranked[:1]
    out = []
    for n in picks:
        if n not in [x for x, _ in out]: out.append((n, cfgs[n]))
    log('selection (export MB): ' + ', '.join(f'{n} {size[n] / 1e6:.0f}' for n, _ in out))
    return out


def phases(summary):
    kt = summary.get('kernel_timeline', [])
    def dur(comm, after=None):
        xs = [e for e in kt if e['comm'] == comm and (after is None or e['start_s'] >= after - 0.5)]
        if not xs: return None
        return dict(start_s=min(e['start_s'] for e in xs), end_s=max(e['end_s'] for e in xs), cpu_s=round(sum(e['cpu_s'] for e in xs), 1),
                    rss_gib=round(max(e['max_rss_bytes'] for e in xs) / 2**30, 2))
    return dur('nanoda_bin'), kt


def run_one(name, cfg):
    d = dict(cfg, enable_nanoda=True); cpath = f'{S}/{name}.json'; json.dump(d, open(cpath, 'w'), indent=1)
    mon = f'{R}/logs/{name}.mon'; env_path = f"{base}/ext/lean4export/.lake/build/bin:{base}/ext/bin:{os.environ['HOME']}/.elan/bin:{os.environ['PATH']}"
    cmd = ['systemd-run', '--user', '--wait', '--pipe', '--collect', f'--unit=nanoda-{name}', '--property=RestrictAddressFamilies=~AF_UNIX',
           f'--property=MemoryMax={a.memmax}', f'--property=RuntimeMaxSec={int(a.max_minutes * 60)}',
           '-E', f'PATH={env_path}', '-E', f"HOME={os.environ['HOME']}", f'--working-directory={root}',
           'python3', '-I', f'{base}/tools/vmamon.py', '--out', mon, '--interval', '0.2', '--label', 'nanoda-' + name, '--',
           'lake', 'env', f'{base}/ext/comparator/.lake/build/bin/comparator', cpath]
    t0 = time.time(); subprocess.run(cmd, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rec = dict(config=name, started=datetime.datetime.fromtimestamp(t0, datetime.timezone.utc).isoformat(timespec='seconds'), wall_s=round(time.time() - t0, 1))
    try: s = json.load(open(mon + '/summary.json'))
    except Exception: s = {}
    text = tail(mon + '/stdout.log', 6000) if os.path.exists(mon + '/stdout.log') else ''
    nano_ok, lean_ok = 'nanoda kernel accepts the solution' in text, 'Lean default kernel accepts the solution' in text
    nano, kt = phases(s)
    leanp = None
    if nano:
        later = [e for e in kt if e['comm'] == 'lean' and e['start_s'] >= nano['end_s'] - 1]
        if not later and s.get('wall_s'):    # Lean's own kernel runs inside the comparator process: its phase is what is left after nanoda finishes
            leanp = dict(start_s=nano['end_s'], end_s=s['wall_s'], cpu_s=None, rss_gib=None)
        if later: leanp = dict(start_s=min(e['start_s'] for e in later), end_s=max(e['end_s'] for e in later), cpu_s=round(sum(e['cpu_s'] for e in later), 1),
                               rss_gib=round(max(e['max_rss_bytes'] for e in later) / 2**30, 2))
    out = 'accepted' if ('Your solution is okay!' in text and nano_ok and lean_ok) else ('timeout' if rec['wall_s'] >= a.max_minutes * 60 - 5 else 'rejected_or_error')
    rec.update(outcome=out, nanoda_accepts=nano_ok, lean_accepts=lean_ok, export_bytes_total=s.get('export_bytes_total'), export_done_s=s.get('export_done_s'),
               nanoda=nano, nanoda_s=round(nano['end_s'] - nano['start_s'], 1) if nano else None, lean_kernel=leanp,
               lean_kernel_s=round(leanp['end_s'] - leanp['start_s'], 1) if leanp else None, cpu_user_s=s.get('children_cpu_user_s'),
               peak_vmas=s.get('peak_per_process_vmas_sampled'), peak_rss_gib=round(max([t['max_rss'] for t in s.get('top_processes', [])] or [0]) / 2**30, 1),
               detail='' if out == 'accepted' else text[-400:])
    open(R + '/all.jsonl', 'a').write(json.dumps(rec) + '\n'); return rec


todo = choose()
done = {json.loads(l)['config'] for l in open(R + '/all.jsonl') if json.loads(l).get('outcome') in ('accepted', 'rejected_or_error')} if os.path.exists(R + '/all.jsonl') else set()
todo = [(n, c) for n, c in todo if a.rerun or n not in done]
log(f"{len(todo)} configurations to run: {', '.join(n for n, _ in todo)}")
if a.dry_run: sys.exit(0)
while a.after_unit and subprocess.run(['systemctl', '--user', 'is-active', '--quiet', a.after_unit]).returncode == 0:
    time.sleep(30)
t_start = time.time()
for n, c in todo:
    if os.path.exists(R + '/STOP'): log('STOP file present; exiting'); break
    if time.time() - t_start > a.budget_hours * 3600: log('time budget used; exiting'); break
    while avail_gib() - a.est_gib < a.reserve_gib: time.sleep(20)
    r = run_one(n, c)
    log(f"{n}: {r['outcome']}, wall {r['wall_s']} s, nanoda {r['nanoda_s']} s, Lean kernel {r['lean_kernel_s']} s, export {(r['export_bytes_total'] or 0) / 1e6:.0f} MB, peak {r['peak_rss_gib']} GiB")
    if r['outcome'] == 'rejected_or_error': log('check failed or errored; see detail in all.jsonl; continuing')
log('done')
