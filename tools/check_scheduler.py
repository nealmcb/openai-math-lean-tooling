#!/usr/bin/env python3
"""check_scheduler: run Comparator checks of already-built configurations in parallel, watching memory, and preempt one if needed.

Purpose: pipeline.py checks a batch only after its build, and one multi-hour check can leave the machine idle. Checks of
configurations whose modules are all built do not depend on the build, so they can run beside it. This scheduler picks such "ready"
configurations (every module of both closures has an .olean), orders them by predicted check time, longest first
(results/check-cost-predictions.csv from tools/predict_check_cost.py), and keeps up to --max-parallel running, each through
tools/run_comparator_batch.py (so each is its own systemd unit, cmp-<config>, in its own cgroup: an oomd or kernel kill of one check
does not take the build or the others with it). Admission: a new check starts only if MemAvailable minus its estimated memory
stays above --reserve-gib. Preemption: if MemAvailable falls below --kill-below-gib or memory pressure (some avg10) exceeds
--kill-psi, the youngest check this scheduler started is stopped (least work lost), recorded as outcome "preempted" in all.jsonl
(not as a rejection) and put back in the queue (at most --max-tries attempts each); starts then pause for --cooldown seconds. It never touches checks it did not start,
including the pipeline's. Configurations that are accepted, already being checked (unit cmp-<config> or a comparator process), or
not yet built are skipped; in --continuous mode it rescans so configurations become ready as the build finishes them.
Events go to results/cmp-all/scheduler.log (JSON lines). --dry-run only prints what would start.
Usage: check_scheduler.py [CONFIG ...] [--max-parallel 2] [--reserve-gib 10] [--est-gib 7] [--kill-below-gib 3] [--kill-psi 25]
                          [--cooldown 300] [--max-tries 3] [--memmax 30G] [--continuous] [--dry-run]       (no CONFIG: every ready configuration)
"""
import os, sys, json, csv, time, subprocess, argparse, datetime
ap = argparse.ArgumentParser(); ap.add_argument('configs', nargs='*')
ap.add_argument('--max-parallel', type=int, default=2); ap.add_argument('--reserve-gib', type=float, default=10); ap.add_argument('--est-gib', type=float, default=7)
ap.add_argument('--kill-below-gib', type=float, default=3); ap.add_argument('--kill-psi', type=float, default=25); ap.add_argument('--cooldown', type=int, default=300)
ap.add_argument('--poll', type=int, default=5); ap.add_argument('--rescan', type=int, default=60); ap.add_argument('--max-tries', type=int, default=3); ap.add_argument('--continuous', action='store_true'); ap.add_argument('--dry-run', action='store_true')
ap.add_argument('--memmax', default=None, help='cap each check\'s memory (systemd MemoryMax, e.g. 30G)')
a = ap.parse_args()
base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')); root = base + '/src/lean'; R = base + '/results/cmp-all'
import re
imp = re.compile(rb"^\s*(?:public\s+|meta\s+)*import\s+(?:public\s+|meta\s+)*(\S+)", re.M)
modpath = lambda m: os.path.join(root, *m.split('.'))
deps_cache = {}


def deps(m):
    if m not in deps_cache:
        try: deps_cache[m] = [x.decode() for x in imp.findall(open(modpath(m) + '.lean', 'rb').read()) if x.decode().startswith(('OAI', 'ComparatorChallenges'))]
        except OSError: deps_cache[m] = []
    return deps_cache[m]


def closure(roots):
    seen, todo = set(), list(roots)
    while todo:
        m = todo.pop()
        if m in seen: continue
        seen.add(m); todo += deps(m)
    return seen


def built(name):
    c = json.load(open(f'{root}/ComparatorChallenges/{name}.json'))
    return all(os.path.exists(os.path.join(root, '.lake/build/lib/lean', *m.split('.')) + '.olean') for m in closure([c['solution_module'], c['challenge_module']]))


def log(ev, **kw):
    kw.update(t=datetime.datetime.now().astimezone().isoformat(timespec='seconds'), event=ev); open(R + '/scheduler.log', 'a').write(json.dumps(kw) + '\n'); print(json.dumps(kw), flush=True)


def accepted():
    out = set()
    for l in open(R + '/all.jsonl'):
        d = json.loads(l)
        if d.get('outcome') == 'accepted': out.add(d['config'])
        else: out.discard(d['config'])
    return out


def running_elsewhere(n):
    return (subprocess.run(['systemctl', '--user', 'is-active', '--quiet', f'cmp-{n}']).returncode == 0
            or subprocess.run(['pgrep', '-f', f'bin/comparator ComparatorChallenges/{n}.json'], capture_output=True).returncode == 0)


def avail_gib():
    for l in open('/proc/meminfo'):
        if l.startswith('MemAvailable:'): return int(l.split()[1]) / 2**20


def psi10(): return float(open('/proc/pressure/memory').readline().split('avg10=')[1].split()[0])


pred = {}
if os.path.exists(base + '/results/check-cost-predictions.csv'):
    pred = {r['config']: float(r['pred_s']) for r in csv.DictReader(open(base + '/results/check-cost-predictions.csv'))}
universe = a.configs or sorted(f[:-5] for f in os.listdir(root + '/ComparatorChallenges') if f.endswith('.json'))
running = {}          # config -> (Popen, start time)
tries = {}; last_kill = 0; last_scan = 0; ready = []
env = dict(os.environ, SKIP_BUILD='1', BATCH_ID='scheduler', **({'CHECK_MEMMAX': a.memmax} if a.memmax else {}))
os.makedirs(R + '/preempted', exist_ok=True)
log('start', configs=len(universe), max_parallel=a.max_parallel, reserve_gib=a.reserve_gib, kill_below_gib=a.kill_below_gib, dry_run=a.dry_run)
while True:
    for n, (p, t0) in list(running.items()):
        if p.poll() is not None:
            del running[n]; acc = n in accepted(); log('finished', config=n, seconds=round(time.time() - t0), accepted=acc)
    if time.time() - last_scan > a.rescan or not ready and not running:             # which configurations can be checked now (cheap enough every minute)
        last_scan = time.time(); done = accepted()
        todo = [n for n in universe if n not in done and n not in running and tries.get(n, 0) < a.max_tries]
        ready = sorted([n for n in todo if built(n) and not running_elsewhere(n)], key=lambda n: -pred.get(n, 0))
    ready = [n for n in ready if n not in running]
    av, ps = avail_gib(), psi10()
    if running and (av < a.kill_below_gib or ps > a.kill_psi):                       # preempt the youngest check this scheduler started
        victim = max(running, key=lambda n: running[n][1])
        log('preempt', config=victim, avail_gib=round(av, 1), psi=ps, ran_s=round(time.time() - running[victim][1]))
        if not a.dry_run:
            open(f'{R}/preempted/{victim}', 'w').close()
            subprocess.run(['systemctl', '--user', 'stop', f'cmp-{victim}.service'])
        last_kill = time.time(); last_scan = 0
    elif ready and len(running) < a.max_parallel and time.time() - last_kill > a.cooldown and av - a.est_gib > a.reserve_gib:
        n = ready.pop(0); tries[n] = tries.get(n, 0) + 1
        log('start check', config=n, attempt=tries[n], predicted_s=round(pred.get(n, 0)), avail_gib=round(av, 1), running=sorted(running))
        if a.dry_run: tries[n] = a.max_tries
        else:
            running[n] = (subprocess.Popen(['python3', '-I', base + '/tools/run_comparator_batch.py', root, R + '/all.jsonl', n], env=env,
                                           stdout=open(R + '/driver.log', 'a'), stderr=subprocess.STDOUT), time.time())
    if not running and not ready and not a.continuous:
        log('idle', note='nothing ready and nothing running'); break
    time.sleep(a.poll)
