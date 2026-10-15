#!/usr/bin/env python3
"""skip_kernel_sample: how much of the library's compile time is Lean's own kernel check?

Purpose: `-D debug.skipKernelTC=true` makes `lean` add declarations without the kernel check (see tools/skip_kernel_test.py), so the CPU time saved
by compiling a module with it, relative to compiling it normally, is the share of that module's compile cost that the kernel accounts for. This
compiles a stratified sample of already-built modules both ways, one at a time on an otherwise quiet machine (each copy is compiled as a scratch module
under scratch/skipkernel-sample/, so the project's build files are untouched), and estimates the library-wide share by weighting each stratum by its
total compile time in results/module-times.csv.gz (laptop wall seconds under load, used only as weights). Strata by first-build seconds:
under 5, 5 to 20, 20 to 60, 60 to 200, over 200. Order of the two compiles alternates between modules to spread cache effects; one run of each, so
single-module numbers are noisy but the weighted sum is not. Output: results/skip-kernel-test/sample.jsonl (one line per module) and a summary line.
Usage: skip_kernel_sample.py [--per-stratum 6,6,6,5,3] [--seed 1]
"""
import os, sys, csv, gzip, json, time, random, shutil, subprocess, resource
base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')); root = base + '/src/lean'
S = base + '/scratch/skipkernel-sample'; R = base + '/results/skip-kernel-test'; os.makedirs(R, exist_ok=True)
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
per = [int(x) for x in arg('--per-stratum', '6,6,6,5,3').split(',')]; rnd = random.Random(int(arg('--seed', '1')))
rows = [r for r in csv.DictReader(gzip.open(base + '/results/module-times.csv.gz', 'rt')) if r['likely_pause_artifact'] != '1' and r['module'].startswith('OAI.')]
edges = [0, 5, 20, 60, 200, 1e9]
strata = [[r for r in rows if edges[i] <= float(r['first_build_s']) < edges[i + 1]] for i in range(5)]
weights = [sum(float(r['first_build_s']) for r in s) for s in strata]
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + '/src/SkipTest'); os.makedirs(S + '/lib/SkipTest')
tc = os.path.expanduser('~/.elan/toolchains/leanprover--lean4---v4.34.1')
lp = subprocess.run(['lake', 'env', 'printenv', 'LEAN_PATH'], cwd=root, capture_output=True, text=True).stdout.strip().splitlines()[-1]
env = dict(os.environ, LEAN_PATH=S + '/lib:' + lp, PATH=f'{tc}/bin:' + os.environ['PATH'])


def compile_(name, skip):
    cmd = ['lean', *(['-D', 'debug.skipKernelTC=true'] if skip else []), '-R', '.', '-o', f'{S}/lib/SkipTest/{name}.olean', f'SkipTest/{name}.lean']
    r0 = resource.getrusage(resource.RUSAGE_CHILDREN); t = time.time()
    p = subprocess.run(cmd, cwd=S + '/src', env=env, capture_output=True, text=True)
    r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    return p.returncode, time.time() - t, (r1.ru_utime - r0.ru_utime) + (r1.ru_stime - r0.ru_stime)


out = open(R + '/sample.jsonl', 'w'); res = [[] for _ in range(5)]; k = 0
for i, s in enumerate(strata):
    for r in rnd.sample(s, min(per[i], len(s))):
        k += 1; name = f'M{k}'; m = r['module']
        open(f'{S}/src/SkipTest/{name}.lean', 'w').write(open(root + '/' + m.replace('.', '/') + '.lean').read())
        order = [False, True] if k % 2 else [True, False]; got = {}
        for skip in order:
            nm = name + ('s' if skip else 'n'); shutil.copy(f'{S}/src/SkipTest/{name}.lean', f'{S}/src/SkipTest/{nm}.lean'); got[skip] = compile_(nm, skip)
        rec = dict(module=m, stratum=i, laptop_s=float(r['first_build_s']), normal=got[False], skip=got[True])
        out.write(json.dumps(rec) + '\n'); out.flush()
        if got[False][0] == 0 and got[True][0] == 0:
            res[i].append((got[False][2], got[True][2], got[False][1], got[True][1]))
            print(f"{m[-50:]:50s} stratum {i} cpu {got[False][2]:7.1f} -> {got[True][2]:7.1f}  wall {got[False][1]:6.1f} -> {got[True][1]:6.1f}", flush=True)
        else: print(f"{m} FAILED {got[False][0]} {got[True][0]}", flush=True)
tot_w = sum(weights); est = 0; estw = 0
for i in range(5):
    if res[i]:
        n = sum(a for a, b, _, _ in res[i]); s = sum(b for a, b, _, _ in res[i]); frac = 1 - s / n
        wn = sum(a for _, _, a, _ in res[i]); ws = sum(b for _, _, _, b in res[i])
        est += weights[i] / tot_w * frac; estw += weights[i] / tot_w * (1 - ws / wn)
        print(f"stratum {i} (laptop {edges[i]}-{edges[i + 1]} s, {len(strata[i])} modules, {weights[i] / 3600:.0f} h): {len(res[i])} sampled, CPU saved {100 * frac:.1f}%, wall saved {100 * (1 - ws / wn):.1f}%")
print(f"weighted estimate of library compile CPU saved by skipping the kernel check: {100 * est:.1f}% (wall {100 * estw:.1f}%)")
