#!/usr/bin/env python3
"""cloud_finish_build: wait for the configuration builds to finish, then build every OAI module that is still missing, in one `lake build`.

Purpose: tools/cloud_run.py (--no-checks) builds the modules the 416 Comparator configurations need (107,978 in-repo modules). The library has 122,457 OAI files
(plus the root module OAI): 7,219 are imported by OAI.lean but needed by no configuration, and 7,262 are reachable from nothing. To have every module built, this
waits for results/cmp-all/BUILDS_DONE, lists the OAI modules (git ls-files) that lack an .olean or .trace, raises vm.max_map_count to 262144 (the root module OAI imports
91,762 modules and needs about 149,000 mappings; the default 65,530 is only right for everything else), and runs one `lake build MODULE...` through the throttled sysroot
(ext/sysroot-throttled, LEAN_SLOTS compile slots, all CPUs) with the profiler wrapper still in place. It writes RESULTS/final-build.log, and RESULTS/ALL_BUILT (with the exit
code and the count still missing) when the build ends. The mapping limit is restored to 65,530 afterwards.
--feather starts it early, while configuration builds are still running, on the safe subset only: the unbuilt modules none of whose unbuilt dependencies (transitively)
is a module of some configuration's closure that is still unbuilt, so it can never compile a module a configuration build is compiling or will compile; no mapping-limit
change, no ALL_BUILT; log to RESULTS/feather.log. The root module OAI is never in that subset. The normal run afterwards (without --feather) builds what is left.
Usage: cloud_finish_build.py [--lean-slots 32] [--wait] [--dry-run] [--feather]
"""
import os, sys, time, json, subprocess, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from priority_build import Resolver
base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')); root = base + '/src/lean'; R = base + '/results/cmp-all'
slots = sys.argv[sys.argv.index('--lean-slots') + 1] if '--lean-slots' in sys.argv else '32'
log = lambda m: print(f"{datetime.datetime.now().astimezone().isoformat(timespec='seconds')} cloud_finish_build: {m}", flush=True)
if '--wait' in sys.argv:
    while not os.path.exists(R + '/BUILDS_DONE'): time.sleep(20)
    log('BUILDS_DONE seen')
    while os.path.exists(R + '/feather.running'): time.sleep(20)          # an early (--feather) build must finish first: never two builds on the same module
    log('no feather build running')
res = Resolver(root)
files = subprocess.run(['git', '-C', root, 'ls-files', 'OAI', 'OAI.lean'], capture_output=True, text=True).stdout.split()
mods = sorted({f[:-5].replace('/', '.') for f in files if f.endswith('.lean')})
todo = [m for m in mods if not res.built(m)]
log(f"{len(mods)} OAI modules, {len(todo)} not built")
if '--feather' in sys.argv:
    sys.setrecursionlimit(100000)
    cfg = {l.strip() for l in open(base + '/results/comparator-solution-closure.txt') if l.strip()}
    ucfg = {m for m in cfg if not res.built(m)}; memo = {}

    def touches(m):          # does m depend, through unbuilt modules, on an unbuilt configuration module?
        if m in memo: return memo[m]
        memo[m] = True       # guards against cycles (none expected)
        r = m in ucfg or any(touches(d) for d in res.imports(m) if not res.built(d))
        memo[m] = r; return r

    todo = [m for m in todo if m != 'OAI' and not touches(m)]
    log(f"feather: {len(ucfg)} configuration modules still unbuilt; {len(todo)} extra modules are safe to build now")
    if '--dry-run' in sys.argv or not todo: sys.exit(0)
    env = dict(os.environ, LEAN_SYSROOT=base + '/ext/sysroot-throttled', LEAN_SLOTS=slots); t = time.time()
    open(R + '/feather.running', 'w').write(str(os.getpid()))
    try: rc = subprocess.run([base + '/ext/sysroot-throttled/bin/lake', 'build', *todo], cwd=root, env=env, stdout=open(R + '/feather.log', 'w'), stderr=subprocess.STDOUT).returncode
    finally: os.remove(R + '/feather.running')
    log(f"feather build exit {rc} after {(time.time() - t) / 3600:.2f} h"); sys.exit(0)
if '--dry-run' in sys.argv or not todo: sys.exit(0)
old = open('/proc/sys/vm/max_map_count').read().strip()
subprocess.run(['sudo', 'sysctl', '-w', 'vm.max_map_count=262144'], check=True, capture_output=True); log(f"vm.max_map_count {old} -> 262144")
env = dict(os.environ, LEAN_SYSROOT=base + '/ext/sysroot-throttled', LEAN_SLOTS=slots)
t = time.time()
rc = subprocess.run([base + '/ext/sysroot-throttled/bin/lake', 'build', *todo], cwd=root, env=env, stdout=open(R + '/final-build.log', 'w'), stderr=subprocess.STDOUT).returncode
left = [m for m in mods if not res.built(m)]
log(f"lake build exit {rc} after {(time.time() - t) / 3600:.2f} h; {len(left)} modules still not built: {left[:5]}")
subprocess.run(['sudo', 'sysctl', '-w', f'vm.max_map_count={old if old != "1048576" else 65530}'], capture_output=True)
open(R + '/ALL_BUILT', 'w').write(json.dumps(dict(exit=rc, missing=len(left), t=datetime.datetime.now().astimezone().isoformat())) + '\n')
