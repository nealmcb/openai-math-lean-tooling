#!/usr/bin/env python3
"""cloud_run: build every Comparator solution and challenge module and check all 416 configurations on one big machine, then stop.

Purpose: the laptop run was throttled by hand. On a machine with 32 or more dedicated cores and plenty of memory this drives the same work with
the critical path in mind, and optionally with the second kernel (nanoda) switched on in every configuration. It does six things:
  1. --nanoda-all: sets `enable_nanoda: true` in every ComparatorChallenges/*.json of THIS checkout (the checkout on the cloud machine), so
     Comparator runs nanoda and then Lean's kernel on every solution. Comparator has no way to skip Lean's kernel.
  2. builds the configurations in priority order with tools/priority_build.py: longest predicted check first (results/check-cost-predictions.csv),
     several `lake build` at once but never two compiling the same module, compiles capped globally at --lean-slots by the throttled sysroot
     (tools/make_throttled_sysroot.sh) and pinned to --build-cpus;
  3. runs tools/check_scheduler.py --continuous beside it: each check starts as soon as every module of its closure has an .olean, longest
     predicted first, --max-parallel at a time, each in its own systemd unit with a memory cap, pinned to --check-cpus (so the builds do not
     load the CPUs a check is timed on); when all builds have ended the scheduler is restarted on all CPUs with --max-parallel-after;
  4. records the phase of every running check (exporting, nanoda running, nanoda finished and accepted or not, Lean kernel running, finished) with
     a time stamp in RESULTS/phases.jsonl, read from the check's output as it appears, so the nanoda result and time are known long before
     a slow Lean-kernel phase ends (tools/cloud_status.sh shows them);
  5. every --sync-minutes uploads RESULTS (without the bulky samples.jsonl) to s3://BUCKET/PREFIX, so data survives the machine;
  6. when the builds have ended and no check unit has been active for --idle-minutes, writes RESULTS/DONE, uploads everything, and (with --shutdown)
     powers the machine off; an instance launched with shutdown behaviour "terminate" then ends. --max-hours is the cost guard.
Needs the environment of cloud_bootstrap.sh and tools/make_throttled_sysroot.sh run once, the check-cost predictions and
results/solution-closure-sizes.jsonl copied from the laptop, and an instance role that can write the bucket.
Usage: cloud_run.py [--no-checks] [--nanoda-all] [--lean-slots 24] [--build-cpus 0-23] [--check-cpus 24-31] [--max-parallel 8] [--max-parallel-after 26]
                    [--max-builds 6] [--check-memmax 110G] [--bucket B --prefix P] [--shutdown] [--max-hours 26] [--dry-run]
"""
import os, sys, csv, json, time, argparse, datetime, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from priority_build import PriorityBuilder
ap = argparse.ArgumentParser()
ap.add_argument('--nanoda-all', action='store_true'); ap.add_argument('--lean-slots', type=int, default=24); ap.add_argument('--build-cpus', default='0-23')
ap.add_argument('--check-cpus', default='24-31'); ap.add_argument('--max-parallel', type=int, default=8); ap.add_argument('--max-parallel-after', type=int, default=26)
ap.add_argument('--max-builds', type=int, default=6); ap.add_argument('--check-memmax', default='110G'); ap.add_argument('--est-gib', type=float, default=12)
ap.add_argument('--reserve-gib', type=float, default=20); ap.add_argument('--bucket', default=None); ap.add_argument('--prefix', default='full-run')
ap.add_argument('--sync-minutes', type=float, default=30); ap.add_argument('--idle-minutes', type=float, default=10); ap.add_argument('--max-hours', type=float, default=26)
ap.add_argument('--shutdown', action='store_true'); ap.add_argument('--no-checks', action='store_true', help='build only: no check scheduler; stops when the builds end (the machine stays up) so exports and checks can run elsewhere'); ap.add_argument('--dry-run', action='store_true'); a = ap.parse_args()
base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')); root = base + '/src/lean'; R = base + '/results/cmp-all'
os.makedirs(R, exist_ok=True); open(R + '/all.jsonl', 'a').close(); t_start = time.time()


def log(m):
    line = f"{datetime.datetime.now().astimezone().isoformat(timespec='seconds')} cloud_run: {m}"
    open(R + '/driver.log', 'a').write(line + '\n'); print(line, flush=True)


def sync(final=False):
    if not a.bucket: return
    ex = [] if final else ['--exclude', '*/samples.jsonl']
    r = subprocess.run(['aws', 's3', 'sync', R, f's3://{a.bucket}/{a.prefix}/', '--only-show-errors', *ex], capture_output=True, text=True)
    log(f"sync {'(final) ' if final else ''}exit {r.returncode} {r.stderr[-200:].strip()}")


def active_checks():
    r = subprocess.run(['systemctl', '--user', 'list-units', '--no-legend', '--state=active', 'cmp-*.service'], capture_output=True, text=True)
    return [l.split()[0][4:-8] for l in r.stdout.splitlines() if l.strip()]


def records():
    last = {}
    for l in open(R + '/all.jsonl'):
        if l.strip(): d = json.loads(l); last[d['config']] = d.get('outcome')
    return last


def start_scheduler(par, cpus):
    cmd = ['python3', '-I', base + '/tools/check_scheduler.py', '--continuous', '--max-parallel', str(par), '--reserve-gib', str(a.reserve_gib), '--est-gib', str(a.est_gib),
           '--kill-below-gib', '6', '--kill-psi', '40', '--cooldown', '60', '--max-tries', '2', '--memmax', a.check_memmax]
    log(f"starting scheduler: parallel {par}, cpus {cpus}")
    return subprocess.Popen(cmd, stdout=open(R + '/scheduler.out', 'a'), stderr=subprocess.STDOUT, env=dict(os.environ, CHECK_CPUS=cpus))


MARKS = [('Exporting', 'export'), ('Running nanoda kernel', 'nanoda_start'), ('nanoda kernel accepts', 'nanoda_accepts'), ('nanoda kernel rejected', 'nanoda_rejected'),
         ('Running Lean default kernel', 'lean_start'), ('Lean default kernel accepts', 'lean_accepts'), ('Lean default kernel rejects', 'lean_rejects'), ('Your solution is okay', 'okay')]
seen_marks = {}


def phase_events():
    """Time-stamp each phase marker of every running check the first time it shows in the check's output (resolution: the poll interval)."""
    for c in active_checks():
        p = f'{R}/logs/{c}.mon/stdout.log'
        if not os.path.exists(p): continue
        txt = open(p, errors='replace').read()
        for pat, name in MARKS:
            if pat in txt and (c, name) not in seen_marks:
                seen_marks[(c, name)] = 1
                open(R + '/phases.jsonl', 'a').write(json.dumps(dict(config=c, event=name, t=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'))) + '\n')


cfgs = sorted(f[:-5] for f in os.listdir(root + '/ComparatorChallenges') if f.endswith('.json'))
if a.nanoda_all and not a.dry_run:
    n = 0
    for c in cfgs:
        p = f'{root}/ComparatorChallenges/{c}.json'; d = json.load(open(p))
        if not d.get('enable_nanoda'): d['enable_nanoda'] = True; json.dump(d, open(p, 'w'), indent=2); n += 1
    log(f"enable_nanoda set to true in {n} of {len(cfgs)} configurations")
pred = {r['config']: float(r['pred_s']) for r in csv.DictReader(open(base + '/results/check-cost-predictions.csv'))}
order = sorted(cfgs, key=lambda c: -pred.get(c, 0))
log(f"{len(cfgs)} configurations; limit {a.max_hours} h; vm.max_map_count {open('/proc/sys/vm/max_map_count').read().strip()}; {os.cpu_count()} cpus; "
    f"builds on cpus {a.build_cpus} with {a.lean_slots} compile slots, checks on cpus {a.check_cpus}; bucket {a.bucket}")
if a.dry_run: sys.exit(0)

pb = PriorityBuilder(base, order, max_builds=a.max_builds, lean_slots=a.lean_slots, build_cpus=a.build_cpus, results=R, log=log)
class _Off:
    def poll(self): return 0
    def terminate(self): pass
    def wait(self): pass


sched = _Off() if a.no_checks else start_scheduler(a.max_parallel, a.check_cpus); builds_done = None; idle_since = None; last_sync = time.time(); last_report = 0
while True:
    if builds_done is None and pb.step():
        builds_done = time.time(); failed = [c for c, rc in pb.done.items() if rc]
        log(f"all builds ended after {(builds_done - t_start) / 3600:.2f} h; {len(failed)} failed: {failed[:10]}")
        if a.no_checks:
            log('builds finished in no-checks mode; stopping the driver (the machine stays up)'); open(R + '/BUILDS_DONE', 'w').write(datetime.datetime.now().astimezone().isoformat() + '\n'); sync(final=True); sys.exit(0)
        sched.terminate(); sched.wait(); sched = start_scheduler(a.max_parallel_after, f'0-{os.cpu_count() - 1}')
    if not a.no_checks and sched.poll() is not None:
        log(f'scheduler exited with {sched.returncode}; restarting')
        sched = start_scheduler(a.max_parallel_after if builds_done else a.max_parallel, f'0-{os.cpu_count() - 1}' if builds_done else a.check_cpus)
    act = active_checks(); rec = records(); phase_events()
    if time.time() - last_report > 600:
        last_report = time.time(); done = sum(1 for v in rec.values() if v == 'accepted')
        log(f"{(time.time() - t_start) / 3600:.2f} h: builds {'running' if builds_done is None else 'done'} ({len(pb.running)} running, {len(pb.pending)} waiting), {len(act)} checks active, "
            f"{done} accepted, {sum(1 for v in rec.values() if v not in ('accepted', 'preempted'))} failed/other, avail {os.popen('grep MemAvailable /proc/meminfo').read().split()[1]} kB")
    if time.time() - last_sync > a.sync_minutes * 60: sync(); last_sync = time.time()
    if builds_done is not None:
        if act: idle_since = None
        elif idle_since is None: idle_since = time.time()
        if idle_since and time.time() - idle_since > a.idle_minutes * 60:
            log(f"builds ended, no check active for {a.idle_minutes} min; {len(rec)} of {len(cfgs)} configurations have a record"); break
    if time.time() - t_start > a.max_hours * 3600:
        log(f'time limit of {a.max_hours} h reached; stopping'); break
    time.sleep(3)
sched.terminate()
for c, (p, u, t) in pb.running.items(): p.terminate()
open(R + '/DONE', 'w').write(datetime.datetime.now().astimezone().isoformat() + '\n')
sync(final=True)
if a.shutdown: log('powering off'); subprocess.run(['sudo', 'shutdown', '-h', '+1'])
