#!/usr/bin/env python3
"""parallelism_profile: how parallel is the REMAINING build, from the import DAG and measured module times.

Purpose: Lake can only compile a module once its imports are built, so parallelism is limited by the DAG shape, not
only by core count. This computes, for the modules in the Comparator solution closure that are not built yet:
total work (core-hours), critical path (longest dependency chain, hours), average parallelism = work / critical path,
the width profile (modules per dependency depth), and a list-scheduling simulation of the build on P cores.
Module times come from "Built X (Ns)" lines in the build logs (they include contention, so they overstate isolated
CPU time when the machine was oversubscribed); time model t = a + b * source_bytes is fitted on them.
Usage: parallelism_profile.py LEAN_ROOT [CORES=16]
"""
import sys, os, re, json, glob, heapq, collections
root = sys.argv[1]; P = int(sys.argv[2]) if len(sys.argv) > 2 else 16
base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
imp = re.compile(rb"^\s*(?:public\s+|meta\s+)*import\s+(?:public\s+|meta\s+)*(\S+)", re.M)
path = lambda m: os.path.join(root, *m.split('.')) + '.lean'
built = lambda m: os.path.exists(os.path.join(root, '.lake/build/lib/lean', *m.split('.')) + '.olean')
sols = [json.load(open(c))['solution_module'] for c in glob.glob(root + '/ComparatorChallenges/*.json')]
sols += [json.load(open(c))['challenge_module'] for c in glob.glob(root + '/ComparatorChallenges/*.json')]
deps, order, state = {}, [], {}
for r in sols:
    st = [(r, 0)]
    while st:
        m, k = st.pop()
        if k:
            order.append(m); continue
        if m in state or not os.path.exists(path(m)): continue
        state[m] = 1
        deps[m] = [x.decode() for x in imp.findall(open(path(m), 'rb').read()) if os.path.exists(path(x.decode()))]
        st.append((m, 1)); st += [(d, 0) for d in deps[m] if d not in state]
# measured times
secs = lambda s: sum(float(n) * {'ms': .001, 's': 1, 'm': 60, 'h': 3600}[u] for n, u in re.findall(r'([\d.]+)(ms|s|m|h)', s))
T = {}
for f in glob.glob(base + '/results/**/*.log', recursive=True):
    for m, t in re.findall(r'Built (\S+) \(([^)]*)\)', open(f, errors='replace').read()):
        T[m] = max(T.get(m, 0), secs(t))
xs = [(os.path.getsize(path(m)), t) for m, t in T.items() if m in deps and os.path.exists(path(m))]
n = len(xs); sx = sum(x for x, _ in xs); sy = sum(y for _, y in xs)
b = (n * sum(x * y for x, y in xs) - sx * sy) / (n * sum(x * x for x, _ in xs) - sx * sx); a = (sy - b * sx) / n
est = lambda m: max(T.get(m) or (a + b * os.path.getsize(path(m))), 1.0)
rem = [m for m in order if not built(m)]
work = sum(est(m) for m in rem)
fin, lvl = {}, {}
for m in order:
    if built(m): fin[m] = 0; lvl[m] = 0; continue
    fin[m] = est(m) + max([fin[d] for d in deps[m]] or [0]); lvl[m] = 1 + max([lvl[d] for d in deps[m]] or [0])
cp = max(fin.values())
print(f"time model from {n} timed modules: t = {a:.1f}s + {b*1e3:.3f}s per KB of source")
print(f"closure modules {len(order)}, unbuilt {len(rem)}; remaining work {work/3600:.0f} core-hours (contention-inflated)")
print(f"critical path {cp/3600:.1f} h; average parallelism = work / critical path = {work/cp:.1f}; ideal wall on {P} cores >= {max(work/P, cp)/3600:.1f} h")
w = collections.Counter(lvl[m] for m in rem)
depth = max(w); widths = [w[i] for i in range(1, depth + 1)]
print(f"dependency depth (levels) {depth}; modules per level: max {max(widths)}, median {sorted(widths)[len(widths)//2]}, levels with fewer than {P} modules: {sum(x < P for x in widths)} of {depth}")
# list scheduling simulation on P cores, priority = longest remaining path (critical-path-first)
children = collections.defaultdict(list); indeg = {}
for m in rem:
    ds = [d for d in deps[m] if not built(d)]; indeg[m] = len(ds)
    for d in ds: children[d].append(m)
tail = {}
for m in reversed(order):
    if built(m): continue
    tail[m] = est(m) + max([tail[c] for c in children[m]] or [0])
ready = [(-tail[m], m) for m in rem if indeg[m] == 0]; heapq.heapify(ready)
running, t, busy_int, last = [], 0.0, 0.0, 0.0
util_samples = []
while ready or running:
    while ready and len(running) < P:
        _, m = heapq.heappop(ready); heapq.heappush(running, (t + est(m), m))
    t2, m = heapq.heappop(running)
    busy_int += len(running) * (t2 - t) + (t2 - t) * 1
    util_samples.append((t, len(running) + 1)); t = t2
    for c in children[m]:
        indeg[c] -= 1
        if indeg[c] == 0: heapq.heappush(ready, (-tail[c], c))
print(f"list-scheduling simulation on {P} cores: wall {t/3600:.1f} h, mean cores busy {work/t:.1f} ({100*work/t/P:.0f}% utilization)")
# utilization over the simulated timeline (deciles)
dec = [sum(c for tt, c in util_samples if t*i/10 <= tt < t*(i+1)/10) / max(1, sum(1 for tt, c in util_samples if t*i/10 <= tt < t*(i+1)/10)) for i in range(10)]
print("mean busy cores by decile of the simulated build:", ' '.join(f"{x:.0f}" for x in dec))

# ---- per-config view: how parallel is each config's own remaining build (what one-config-at-a-time scheduling sees)
rows = []
for c in glob.glob(root + '/ComparatorChallenges/*.json'):
    d = json.load(open(c)); seen, st = set(), [d['solution_module'], d['challenge_module']]
    while st:
        m = st.pop()
        if m in seen or m not in deps or built(m): continue
        seen.add(m); st += deps[m]
    if not seen: continue
    wk = sum(est(m) for m in seen); cpth = max(fin[m] for m in seen)
    rows.append((len(seen), wk, cpth, wk / cpth, os.path.basename(c)[:-5]))
rows.sort()
q = lambda i: rows[int(i * (len(rows) - 1))]
print(f"\nper-config (unbuilt configs: {len(rows)}): modules to build / work core-h / critical path h / avg parallelism")
for lab, i in (('smallest', 0), ('25%', .25), ('median', .5), ('75%', .75), ('90%', .9), ('largest', 1)):
    r = q(i); print(f"  {lab:9s} {r[0]:6d} modules  work {r[1]/3600:6.2f}  cp {r[2]/3600:5.2f}  parallelism {r[3]:5.1f}  ({r[4]})")
print(f"  configs whose own build averages fewer than {P} ready modules: {sum(r[3] < P for r in rows)} of {len(rows)}")
print(f"  sum of per-config work (overlaps counted repeatedly): {sum(r[1] for r in rows)/3600:.0f} core-h")
