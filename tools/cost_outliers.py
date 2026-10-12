#!/usr/bin/env python3
"""cost_outliers: which Comparator configurations cost much more (or less) than their size predicts, and does export size explain it?

Purpose: check time spans about 100x (median ~3 min, slowest ~4.7 h) and peak memory about 4x, and neither tracks line counts or module
counts well. If cost is a signal of proof style (structural proofs versus large computational certificates) it is worth a map of which
configurations sit far from the trend. This joins, per accepted configuration, active check time, check memory, closure compile time,
solution size and (where recorded) the bytes lean4export streams, then:
  1. prints quantiles of check time and memory;
  2. fits log10(check time) on log10(closure compile time), over configurations whose closure is at least 90% timed, and lists the largest residuals in both directions (slower and faster than
     compile cost predicts);
  3. does the same for check memory on solution size;
  4. reports seconds per exported MB and its rank correlation with check time, but only over the configurations that have an export
     size (n is printed; the early checks lost it to a monitor bug, so a backfill is needed before this part is conclusive).
Reads results/check-time-factors.csv (run tools/check_time_factors.py first) and results/cmp-all/configs.csv. Writes
results/cost-outliers.csv. Association only; a residual is a pointer to read the proof, not an explanation.
Usage: cost_outliers.py [--top 12]
"""
import os, csv, math, argparse
import numpy as np
ap = argparse.ArgumentParser(); ap.add_argument('--top', type=int, default=12); a = ap.parse_args()
base = '/home/srv/s/math/openai-math'
fac = {r['config']: r for r in csv.DictReader(open(base + '/results/check-time-factors.csv'))}
cfg = {r['config']: r for r in csv.DictReader(open(base + '/results/cmp-all/configs.csv'))}
fl = lambda v: float(v) if v not in (None, '') else None


def ranks(v):
    o = np.argsort(v, kind='stable'); r = np.empty(len(v)); r[o] = np.arange(1, len(v) + 1)
    for x in set(v):                                   # average the ranks of ties
        m = [i for i, y in enumerate(v) if y == x]
        if len(m) > 1: r[m] = r[m].mean()
    return r


def spearman(x, y): return float(np.corrcoef(ranks(list(x)), ranks(list(y)))[0, 1])


rows = []
for n, f in fac.items():
    c = cfg.get(n, {})
    rows.append(dict(config=n, check_s=fl(f['check_active_s']), rss_gib=fl(f['check_rss_gib']), closure_modules=int(f['closure_modules']), timed=int(f['closure_timed_modules']),
                     compile_s=fl(f['closure_compile_s']), solution_kb=fl(f['solution_src_kb']), solution_lines=fl(c.get('solution_lines')),
                     theorems=int(f['theorem_names']), export_mb=fl(c.get('export_mb_total'))))
q = lambda v, p: float(np.percentile(v, p))
t = [r['check_s'] for r in rows]; m = [r['rss_gib'] for r in rows if r['rss_gib']]
print(f"{len(rows)} accepted configurations")
print(f"check time s   : p10 {q(t, 10):.0f}  median {q(t, 50):.0f}  p90 {q(t, 90):.0f}  p99 {q(t, 99):.0f}  max {max(t):.0f}  (max/median {max(t) / q(t, 50):.0f}x)")
print(f"check memory GiB: p10 {q(m, 10):.1f}  median {q(m, 50):.1f}  p90 {q(m, 90):.1f}  max {max(m):.1f}  (n={len(m)})")
for r in rows: r['bytes_per_line'] = 1024 * r['solution_kb'] / r['solution_lines'] if r['solution_lines'] else None


def fit(rows, xk, yk, label, unit):
    use = [r for r in rows if r[xk] and r[yk] and r[xk] > 0 and r[yk] > 0]
    x = np.log10([r[xk] for r in use]); y = np.log10([r[yk] for r in use]); b, a0 = np.polyfit(x, y, 1)
    res = y - (a0 + b * x); sd = res.std()
    for r, e in zip(use, res): r['res_' + yk] = float(e)
    print(f"\n{label}: log10({yk}) = {a0:.2f} + {b:.2f}*log10({xk}), n={len(use)}, rank correlation {spearman(x, y):.2f}, residual sd {sd:.2f} decades")
    o = sorted(use, key=lambda r: -r['res_' + yk])
    for title, sel in (('costs MORE than the trend (read these first)', o[:a.top]), ('costs LESS than the trend', o[-a.top // 2:])):
        print(f"  {title}:")
        print(f"    {'config':28s} {yk:>9s} {xk:>11s} {'x trend':>8s} {'closure':>7s} {'soln KB':>8s} {'B/line':>6s} {'thms':>4s}")
        for r in sel:
            print(f"    {r['config']:28s} {r[yk]:9.1f} {r[xk]:11.1f} {10 ** r['res_' + yk]:8.1f} {r['closure_modules']:7d} {r['solution_kb']:8.0f} {r['bytes_per_line'] or 0:6.0f} {r['theorems']:4d}")


full = [r for r in rows if r['timed'] >= 0.9 * r['closure_modules']]            # a partial sum of compile times would fake a cheap closure
print(f"\n{len(rows) - len(full)} configurations excluded from the compile-time fit: under 90% of their closure has a recorded compile time")
fit(full, 'compile_s', 'check_s', 'check time vs the closure compile time', 's')
fit([r for r in rows if r['rss_gib']], 'solution_kb', 'rss_gib', 'check memory vs the solution source size', 'GiB')
ex = [r for r in rows if r['export_mb']]
print(f"\nexport size: {len(ex)} of {len(rows)} configurations have it", end='')
if len(ex) >= 10:
    rate = [r['check_s'] / r['export_mb'] for r in ex]
    print(f"; seconds per exported MB: median {q(rate, 50):.2f}, range {min(rate):.2f} to {max(rate):.2f}")
    print(f"  rank correlation of check time with export MB: {spearman([r['export_mb'] for r in ex], [r['check_s'] for r in ex]):.2f}")
    print(f"  rank correlation of check time with closure compile time on the same configs: {spearman([r['compile_s'] for r in ex], [r['check_s'] for r in ex]):.2f}")
else:
    print(" - too few to say anything; backfill needed (re-run only lean4export for the earlier checks)")
cols = ['config', 'check_s', 'rss_gib', 'closure_modules', 'compile_s', 'solution_kb', 'solution_lines', 'bytes_per_line', 'theorems', 'export_mb', 'res_check_s', 'res_rss_gib']
with open(base + '/results/cost-outliers.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, cols, extrasaction='ignore'); w.writeheader()
    for r in sorted(rows, key=lambda r: -r['check_s']): w.writerow({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})
print(f"\nwrote {base}/results/cost-outliers.csv")
