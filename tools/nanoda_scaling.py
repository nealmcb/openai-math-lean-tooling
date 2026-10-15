#!/usr/bin/env python3
"""nanoda_scaling: how does nanoda's checking time fall as it is given more threads?

Purpose: Comparator hard-codes `num_threads: 4` in the nanoda config, and nanoda checks the export's declarations in parallel by letting each
thread take the next declaration from a shared counter (ext/nanoda_lib/src/tc.rs), so extra threads help only while there are enough
declarations of comparable cost. This exports a configuration's solution once with lean4export (the same targets Comparator passes: the theorem names,
permitted axioms, primitives, Quot declarations and definition names), then runs nanoda_bin on that file with 1, 2, 4, 8, ... threads, each under
vmamon-free plain timing (wall seconds, user+system CPU seconds from rusage, peak RSS), and prints the speed-up over 1 thread (or over the lowest
count given) and the parallel efficiency. The export is kept in scratch/nanoda-scaling/CONFIG.export and the results appended to
results/nanoda-scaling.jsonl. Needs the configuration's closure built. Run on a quiet machine.
With --export-only it stops after writing the export (to ship it to another machine that has only nanoda_bin). If ext/bin/nanoda_bin.timing exists
(nanoda built with tools/patches/nanoda-stack-and-decl-times.patch) it is used, with NANODA_DECL_TIMES=scratch/nanoda-scaling/CONFIG.N.times, which records the
check time of every declaration and the length of the parallel phase (the rest of the wall time is reading the export), so the declaration structure
(how much one declaration can hold up the others) is known for each run.
On a machine without the repository, put CONFIG.export in scratch/nanoda-scaling/ (and nanoda_bin.timing in ext/bin/) and it runs the thread series on that.
Each run is killed after --timeout seconds (default 3600) and recorded with exit 137.
The checker stack is 1024 MiB (NANODA_STACK_MB; --stack-mb N to change) so a deep reduction fails by its own limits, not the 16 MiB default.
Usage: nanoda_scaling.py CONFIG [--threads 1,2,4,8,16] [--export-only] [--timeout 3600] [--stack-mb 1024]
"""
import os, sys, json, time, resource, subprocess
base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')); root = base + '/src/lean'
name = sys.argv[1]; arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
threads = [int(x) for x in arg('--threads', '1,2,4,8,16').split(',')]
cfgp = f'{root}/ComparatorChallenges/{name}.json'
cfg = json.load(open(cfgp)) if os.path.exists(cfgp) else dict(permitted_axioms=['propext', 'Quot.sound', 'Classical.choice'])   # on a machine without the repository: only a shipped export
D = base + '/scratch/nanoda-scaling'; os.makedirs(D, exist_ok=True)
QUOT = ['Quot', 'Quot.mk', 'Quot.lift', 'Quot.ind']
PRIM = ['Nat.add', 'Nat.sub', 'Nat.mul', 'Nat.pow', 'Nat.gcd', 'Nat.div', 'Nat.mod', 'Nat.beq', 'Nat.ble', 'Nat.land', 'Nat.lor', 'Nat.xor', 'Nat.shiftLeft',
        'Nat.shiftRight', 'String.ofList', 'Char.ofNat', 'List', 'eagerReduce', 'Nat', 'String', 'String.mk', 'Char', 'optParam', 'autoParam', 'semiOutParam', 'outParam']
env = dict(os.environ, PATH=f"{base}/ext/lean4export/.lake/build/bin:{base}/ext/bin:{os.path.expanduser('~')}/.elan/bin:{os.environ['PATH']}")
exp = f'{D}/{name}.export'
if not os.path.exists(exp) and not os.path.exists(cfgp): sys.exit(f'{exp} is missing and there is no repository to export from')
export_s = None
if not os.path.exists(exp):
    t = time.time()
    with open(exp, 'wb') as f:
        subprocess.run(['lake', 'env', 'lean4export', cfg['solution_module'], '--', *(QUOT + cfg['theorem_names'] + cfg.get('permitted_axioms', []) + PRIM + (cfg.get('definition_names') or []))],
                       cwd=root, env=env, stdout=f, stderr=subprocess.DEVNULL)
    export_s = round(time.time() - t, 1); print(f"exported {os.path.getsize(exp) / 1e6:.0f} MB in {export_s} s", flush=True)
    open(base + '/results/nanoda-scaling.jsonl', 'a').write(json.dumps(dict(config=name, export_s=export_s, export_mb=round(os.path.getsize(exp) / 1e6))) + '\n')
if '--export-only' in sys.argv: sys.exit(0)
base_t = None
NB = base + '/ext/bin/nanoda_bin.timing'; NANODA = NB if os.path.exists(NB) else 'nanoda_bin'
for n in threads:
    json.dump(dict(use_stdin=False, export_file_path=exp, permitted_axioms=cfg.get('permitted_axioms', []), unpermitted_axiom_hard_error=True, num_threads=n,
                   nat_extension=True, string_extension=True), open(f'{D}/{name}.{n}.json', 'w'))
    r0 = resource.getrusage(resource.RUSAGE_CHILDREN); t = time.time()
    p = subprocess.Popen(['timeout', '-s', 'KILL', arg('--timeout', '3600'), NANODA, f'{D}/{name}.{n}.json'], env=dict(env, NANODA_STACK_MB=arg('--stack-mb', '1024'), NANODA_DECL_TIMES=f'{D}/{name}.{n}.times'), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _, status, ru = os.wait4(p.pid, 0); wall = time.time() - t
    cpu = ru.ru_utime + ru.ru_stime; rc = os.waitstatus_to_exitcode(status)
    base_t = base_t or wall * threads[0]
    rec = dict(config=name, threads=n, exit=rc, wall_s=round(wall, 1), cpu_s=round(cpu, 1), cores_used=round(cpu / wall, 2), rss_gib=round(ru.ru_maxrss / 2**20, 2),
               speedup=round((base_t / threads[0]) / wall, 2))
    open(base + '/results/nanoda-scaling.jsonl', 'a').write(json.dumps(rec) + '\n')
    print(f"{name} threads {n:2d}: exit {rc} wall {wall:7.1f} s  cpu {cpu:7.1f} s  cores {cpu / wall:5.2f}  rss {ru.ru_maxrss / 2**20:5.2f} GiB  speed-up over {threads[0]} thread(s) {(base_t / threads[0]) / wall:.2f}", flush=True)
