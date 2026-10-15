#!/usr/bin/env python3
"""nanoda_thread_model: predict nanoda's wall time for any thread count from one run's per-declaration times, and suggest a thread count.

Purpose: nanoda (tools/patches/nanoda-stack-and-decl-times.patch) can write the time spent on each declaration (NANODA_DECL_TIMES). Its threads take the
declarations in export order from a shared counter, so the wall time of the parallel phase at N threads can be simulated exactly from those times:
each declaration, in index order, starts on the thread that becomes free first. Adding the serial setup (reading the export: wall time minus the
parallel phase of the measured run) gives a predicted total. Measured times include contention, so the model is run on a 4-thread (little contention)
and on a high-thread-count file when both exist. For each N it prints the predicted wall time and the speed-up over 4 threads; "suggested" is the
smallest N whose predicted wall time is within --tol (default 5%) of the best, i.e. where extra threads stop paying. The lower bound for any N is
max(longest declaration, total/N): it names the declaration that limits the check. Reads the file nanoda writes with NANODA_DECL_TIMES: either lines "index<TAB>microseconds<TAB>name" after a first
line "#scope<TAB>microseconds<TAB>..." (first version) or the streaming version, lines B (begin: idx, thread, microseconds since the phase began, name), E (end:
idx, thread, microseconds spent, name) and S (length of the parallel phase); a B with no E names a declaration that was in progress when nanoda died. Usage: nanoda_thread_model.py FILE.times [--wall SECONDS_OF_THAT_RUN] [--tol 0.05] [--compare MEASURED=4:193.7,8:137.6,...]
"""
import sys, heapq
arg = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
L = open(sys.argv[1]).read().splitlines()
if L[0].startswith('#scope'):                                 # first format: one line per declaration at the end
    scope = int(L[0].split('\t')[1]) / 1e6
    rows = sorted(((int(r.split('\t')[0]), int(r.split('\t')[1]), r.split('\t')[2]) for r in L[1:]))
else:                                                          # streaming format: B (begin), E (end, with microseconds), S (end of the parallel phase)
    E = [r.split('\t', 4) for r in L if r.startswith('E\t')]; B = {r.split('\t', 4)[1] for r in L if r.startswith('B\t')}
    rows = sorted((int(r[1]), int(r[3]), r[4]) for r in E)
    S = [int(r.split('\t')[1]) for r in L if r.startswith('S\t')]
    scope = S[0] / 1e6 if S else max(int(r.split('\t', 4)[3]) for r in L if r.startswith('B\t')) / 1e6
    done_idx = {x[1] for x in E}
    unfinished = [r.split('\t', 4)[4] for r in L if r.startswith('B\t') and r.split('\t', 4)[1] not in done_idx]
    if unfinished: print(f"{len(unfinished)} declarations began and did not finish (crash or kill): {unfinished[:5]}")
us = [u for _, u, _ in rows]; tot = sum(us) / 1e6; longest = max(rows, key=lambda r: r[1])
wall = float(arg('--wall', scope)); setup = max(0.0, wall - scope); tol = float(arg('--tol', 0.05))


def makespan(n):
    h = [0] * n; heapq.heapify(h)
    for u in us: heapq.heapreplace(h, h[0] + u)
    return max(h) / 1e6


print(f"{len(rows)} declarations, sum of declaration times {tot:.1f} s, parallel phase measured {scope:.1f} s, setup {setup:.1f} s")
print(f"longest declaration {longest[1] / 1e6:.1f} s ({100 * longest[1] / 1e6 / tot:.1f}% of the sum): {longest[2][:80]}")
cands = [1, 2, 4, 8, 16, 32, 64, 128]; pred = {n: makespan(n) + setup for n in cands}; best = min(pred.values())
base = pred[4]
for n in cands: print(f"  {n:3d} threads: predicted wall {pred[n]:8.1f} s   speed-up over 4: {base / pred[n]:5.2f}   bound max(longest, sum/N)+setup {max(longest[1] / 1e6, tot / n) + setup:8.1f} s")
print('suggested threads:', min(n for n in cands if pred[n] <= best * (1 + tol)))
if arg('--compare'):
    print('measured vs predicted:', ', '.join(f"{k}: {v} vs {pred[int(k)]:.1f}" for k, v in (x.split(':') for x in arg('--compare').split(','))))
