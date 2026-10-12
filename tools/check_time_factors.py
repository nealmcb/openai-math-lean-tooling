#!/usr/bin/env python3
"""check_time_factors: which properties of a Comparator configuration go with a long check?

Purpose: Comparator check time varies from seconds to hours and is not predicted by closure size. This joins, per accepted
configuration, the active (unpaused) check time with candidate explanatory features: import-closure size and source bytes,
the solution module's own size, the summed and maximum compile time of the closure's modules (a proxy for proof/elaboration
weight, from results/module-times.csv.gz), the number of theorem names being checked, whether the second kernel (nanoda) is
enabled, and the memory the check used. It prints the slowest checks and Spearman rank correlations, and writes
results/check-time-factors.csv. Rank correlation shows association only, not cause.
Usage: check_time_factors.py
"""
import os, re, csv, gzip, json, glob, statistics as st
base = '/home/srv/s/math/openai-math'; root = base + '/src/lean'
imp = re.compile(rb"^\s*(?:public\s+|meta\s+)*import\s+(?:public\s+|meta\s+)*(\S+)", re.M)
cache = {}
def deps(m):
    if m not in cache:
        p = os.path.join(root, *m.split('.')) + '.lean'
        cache[m] = [x.decode() for x in imp.findall(open(p, 'rb').read()) if os.path.exists(os.path.join(root, *x.decode().split('.')) + '.lean')] if os.path.exists(p) else []
    return cache[m]
def closure(roots):
    seen, todo = set(), list(roots)
    while todo:
        m = todo.pop()
        if m in seen: continue
        seen.add(m); todo += deps(m)
    return seen
mt = {r['module']: float(r['first_build_s']) for r in csv.DictReader(gzip.open(base + '/results/module-times.csv.gz', 'rt')) if r['likely_pause_artifact'] != '1'}
size = lambda m: os.path.getsize(os.path.join(root, *m.split('.')) + '.lean')
rows = []
for r in csv.DictReader(open(base + '/results/cmp-all/configs.csv')):
    if r['status'] != 'accepted' or not r['check_active_s']: continue
    cfg = json.load(open(f"{root}/ComparatorChallenges/{r['config']}.json"))
    cl = closure([cfg['solution_module'], cfg['challenge_module']])
    ct = [mt[m] for m in cl if m in mt]
    rows.append(dict(config=r['config'], check_active_s=float(r['check_active_s']), closure_modules=len(cl), closure_src_kb=sum(size(m) for m in cl) / 1024,
                     solution_src_kb=size(cfg['solution_module']) / 1024, closure_compile_s=sum(ct), max_module_compile_s=max(ct or [0]),
                     theorem_names=len(cfg['theorem_names']), nanoda=int(bool(cfg.get('enable_nanoda'))),
                     check_rss_gib=float(r['check_peak_rss_gib']) if r['check_peak_rss_gib'] else None))
def rank(v):
    o = sorted(range(len(v)), key=lambda i: v[i]); rk = [0.0] * len(v); i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]: j += 1
        for k in range(i, j + 1): rk[o[k]] = (i + j) / 2 + 1
        i = j + 1
    return rk
def spearman(x, y):
    rx, ry = rank(x), rank(y); mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry)); den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** .5
    return num / den if den else 0.0
cols = list(rows[0])
with open(base + '/results/check-time-factors.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, cols); w.writeheader(); [w.writerow({k: (round(v, 1) if isinstance(v, float) else v) for k, v in r.items()}) for r in rows]
print(f"{len(rows)} accepted configurations\n\nslowest 10 by active check time:")
print(f"{'config':26s} {'check s':>8s} {'modules':>7s} {'closure KB':>10s} {'soln KB':>8s} {'compile s':>9s} {'max mod s':>9s} {'thms':>4s} {'GiB':>5s}")
for r in sorted(rows, key=lambda r: -r['check_active_s'])[:10]:
    print(f"{r['config']:26s} {r['check_active_s']:8.0f} {r['closure_modules']:7d} {r['closure_src_kb']:10.0f} {r['solution_src_kb']:8.0f} {r['closure_compile_s']:9.0f} {r['max_module_compile_s']:9.0f} {r['theorem_names']:4d} {r['check_rss_gib'] or 0:5.1f}")
print("\nSpearman rank correlation with check time (all accepted configurations):")
y = [r['check_active_s'] for r in rows]
for k in ('closure_modules', 'closure_src_kb', 'solution_src_kb', 'closure_compile_s', 'max_module_compile_s', 'theorem_names', 'nanoda'):
    print(f"  {k:22s} {spearman([r[k] for r in rows], y):6.2f}")
v = [(r['check_rss_gib'], r['check_active_s']) for r in rows if r['check_rss_gib']]
print(f"  {'check_rss_gib':22s} {spearman([a for a, _ in v], [b for _, b in v]):6.2f}   (n={len(v)}; only checks run after the monitor fix)")
big = [r for r in rows if r['check_active_s'] >= 1800]
print(f"\nchecks over 30 min: {len(big)} of {len(rows)}; median closure {st.median(r['closure_modules'] for r in big):.0f} modules vs {st.median(r['closure_modules'] for r in rows):.0f} overall; "
      f"median theorem names {st.median(r['theorem_names'] for r in big):.0f} vs {st.median(r['theorem_names'] for r in rows):.0f}")
