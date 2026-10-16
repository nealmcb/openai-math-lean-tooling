#!/usr/bin/env python3
"""export_vs_check: how well do the size and contents of a solution's export predict the Comparator check time?

Purpose: REPORT.md section 3c asks what makes a check expensive. tools/export_probe.py measures, for every configuration whose closure
is built, the bytes of the solution export and counts of its record kinds (results/export-probe.csv); results/cmp-all/configs.csv has
the active check time of each accepted configuration. This prints rank (Spearman) correlations of check time with the export size and
with each count (expression nodes, theorem records, natural-number literals, and the number of distinct applications of
`of_decide_eq_true`, the proof term `decide +kernel` leaves behind), the check time per exported MB, and the configurations whose check
time is far above or below what their export size predicts (log-log fit). Read-only; prints to stdout.
Usage: export_vs_check.py [--top 8]
"""
import csv, math, sys, os
base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
top = int(sys.argv[sys.argv.index('--top') + 1]) if '--top' in sys.argv else 8
chk = {r['config']: float(r['check_active_s']) for r in csv.DictReader(open(base + '/results/cmp-all/configs.csv')) if r['check_active_s']}
pr = {r['config']: r for r in csv.DictReader(open(base + '/results/export-probe.csv')) if r['exit'] == '0'}
names = sorted(n for n in pr if n in chk)


def ranks(v):
    o = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]: j += 1
        for k in range(i, j + 1): r[o[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def pearson(a, b):
    n = len(a); ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a)); sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


t = [chk[n] for n in names]
print(f"{len(names)} accepted configurations with both an export measurement and a check time")
for col in ['export_bytes', 'expr_nodes', 'thm', 'def', 'nat_lits', 'of_decide_eq_true_apps']:
    x = [float(pr[n][col]) for n in names]
    print(f"  rank correlation of check time with {col:24s} {pearson(ranks(x), ranks(t)):.2f}")
mb = sorted((chk[n] / (float(pr[n]['export_bytes']) / 1e6), n) for n in names)
print(f"check seconds per exported MB: min {mb[0][0]:.2f} ({mb[0][1]}), median {mb[len(mb) // 2][0]:.2f}, max {mb[-1][0]:.1f} ({mb[-1][1]})")
lx = [math.log10(float(pr[n]['export_bytes'])) for n in names]; ly = [math.log10(c) for c in t]
mx, my = sum(lx) / len(lx), sum(ly) / len(ly); slope = sum((a - mx) * (b - my) for a, b in zip(lx, ly)) / sum((a - mx) ** 2 for a in lx)
res = sorted((b - (my + slope * (a - mx)), n) for a, b, n in zip(lx, ly, names))
print(f"log-log fit of check time on export bytes: slope {slope:.2f}; residual sd {math.sqrt(sum(r * r for r, _ in res) / len(res)):.2f} decades")
print("far above the fit:", ', '.join(f"{n} x{10 ** r:.0f} ({pr[n]['of_decide_eq_true_apps']} decide apps)" for r, n in res[::-1][:top]))
print("far below the fit:", ', '.join(f"{n} x{10 ** r:.2f}" for r, n in res[:top]))
