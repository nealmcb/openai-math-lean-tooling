#!/usr/bin/env python3
"""eta_critical_path: lower-bound ETA for an in-progress `lake build` from the import graph.

Purpose: build-time estimates from a recent job rate are unreliable because parallelism
collapses near the top of a dependency chain. This computes (a) total remaining work /
cores and (b) the critical path through unbuilt modules, using per-module times parsed from
the build log and a fitted time-vs-import-closure model for modules not yet built.
ETA >= max(total/cores, critical path).  Usage: eta_critical_path.py LEAN_ROOT LOG ROOT_MODULE [cores]
"""
import sys, re, os, math
root, log, top = sys.argv[1:4]; cores = int(sys.argv[4]) if len(sys.argv) > 4 else 16
imp = re.compile(rb"^\s*(?:public\s+|meta\s+)*import\s+(?:public\s+|meta\s+)*(\S+)", re.M)
path = lambda m: os.path.join(root, *m.split('.')) + '.lean'
edges, order, state, stack = {}, [], {}, [(top, False)]
while stack:
    m, done = stack.pop()
    if done: order.append(m); continue
    if m in state or not os.path.exists(path(m)): continue
    state[m] = 1
    edges[m] = [d.decode() for d in imp.findall(open(path(m), 'rb').read()) if os.path.exists(path(d.decode()))]
    stack.append((m, True)); stack += [(d, False) for d in edges[m] if d not in state]
clos = {}
bits, idx = {}, {m: i for i, m in enumerate(order)}
for m in order:
    b = 1 << idx[m]
    for d in edges[m]: b |= bits[d]
    bits[m] = b; clos[m] = bin(b).count('1')
def secs(s):
    t = 0
    for n, u in re.findall(r'([\d.]+)(ms|s|m|h)', s): t += float(n) * {'ms': .001, 's': 1, 'm': 60, 'h': 3600}[u]
    return t
times = {}
for l in open(log, errors='replace'):
    m = re.match(r'\S+ \[\d+/\d+\] Built (\S+) \((.*)\)', l)
    if m: times[m[1]] = secs(m[2])
built = {m for m in order if os.path.exists(os.path.join(root, '.lake/build/lib/lean', *m.split('.')) + '.olean')}
# fit t ~ a + b*closure on built-with-times (least squares)
xs = [(clos[m], times[m]) for m in times if m in clos]
n = len(xs); sx = sum(x for x, _ in xs); sy = sum(y for _, y in xs)
b = (n * sum(x * y for x, y in xs) - sx * sy) / (n * sum(x * x for x, _ in xs) - sx * sx); a = (sy - b * sx) / n
est = lambda m: max(times.get(m, a + b * clos[m]), 1.0)
rem = [m for m in order if m not in built]
work = sum(est(m) for m in rem)
fin = {}
for m in order:   # earliest finish, infinite cores
    fin[m] = (0 if m in built else est(m)) + max([fin[d] for d in edges[m]] or [0])
print(f"built {len(built)}/{len(order)} remaining {len(rem)}; time model t={a:.1f}+{b:.4f}*closure (n={n})")
print(f"remaining work {work/3600:.2f} core-h; /{cores} cores = {work/cores/60:.0f} min (perfect packing)")
print(f"critical path (infinite cores) = {fin[top]/60:.0f} min -> ETA >= {max(work/cores, fin[top])/60:.0f} min")
