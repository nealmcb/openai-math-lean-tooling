#!/usr/bin/env python3
"""cost_table: what does it cost to check one OpenAI/math result? A Markdown table by configuration size, for the README.

Purpose: someone deciding whether to run Comparator on a result needs a resource estimate before starting. This buckets the accepted
configurations by in-repo closure size (the OAI modules that must be built; Mathlib comes from the cache) and prints, per bucket, the
number of configurations, median closure size, the summed compile time of the closure in CPU-hours (wall-clock times measured under
load, so an upper bound on isolated cost, and divisible across cores), the Comparator check time (median, 90th percentile, maximum;
unpaused time) and the check memory (median, maximum). Reads results/check-time-factors.csv; per-configuration rows are in
results/cost-outliers.csv. Configurations whose closure is under 90% timed are left out of the compile-time column only.
Usage: cost_table.py
"""
import csv, statistics as st
import numpy as np
base = '/home/srv/s/math/openai-math'
rows = list(csv.DictReader(open(base + '/results/check-time-factors.csv')))
for r in rows:
    r['m'] = int(r['closure_modules']); r['t'] = float(r['check_active_s']); r['g'] = float(r['check_rss_gib']) if r['check_rss_gib'] else None
    r['c'] = float(r['closure_compile_s']) / 3600 if int(r['closure_timed_modules']) >= .9 * r['m'] else None
buckets = [('up to 100 modules', 0, 100), ('101 to 500', 101, 500), ('501 to 2,000', 501, 2000), ('over 2,000', 2001, 10**9)]
mn = lambda s: f"{s / 60:.0f} min" if s < 7200 else f"{s / 3600:.1f} h"
print(f"| Closure size (OAI modules) | Configs | Median closure | Compile CPU time, median (max) | Check time, median / p90 / max | Check memory, median (max) |")
print("|---|---|---|---|---|---|")
for name, lo, hi in buckets:
    b = [r for r in rows if lo <= r['m'] <= hi]
    if not b: continue
    t = [r['t'] for r in b]; g = [r['g'] for r in b if r['g']]; c = [r['c'] for r in b if r['c'] is not None]
    print(f"| {name} | {len(b)} | {st.median(r['m'] for r in b):.0f} | {st.median(c):.1f} h ({max(c):.0f} h) | {mn(st.median(t))} / {mn(float(np.percentile(t, 90)))} / {mn(max(t))} | {st.median(g):.1f} GiB ({max(g):.0f} GiB) |")
t = [r['t'] for r in rows]; g = [r['g'] for r in rows if r['g']]
print(f"| all {len(rows)} accepted | {len(rows)} | {st.median(r['m'] for r in rows):.0f} | | {mn(st.median(t))} / {mn(float(np.percentile(t, 90)))} / {mn(max(t))} | {st.median(g):.1f} GiB ({max(g):.0f} GiB) |")
