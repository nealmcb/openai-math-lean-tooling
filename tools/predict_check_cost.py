#!/usr/bin/env python3
"""predict_check_cost: guess which not-yet-checked Comparator configurations will be slow, from properties of their source.

Purpose: one check (PlanarPacking) has run for 9+ hours while the pipeline waited on it, and earlier outliers (MUBSix 4.7 h) show
that check time is not predicted by closure size. If the slow checks can be recognised before they run, they can be started early
and in parallel with the rest instead of discovered late. The features here need no build and no check: for every module in the
union of the configurations' import closures it counts the uses of `decide +kernel` (kernel evaluation) and the source bytes (each
file is read once, about 1 GB in all; the per-module table is written to results/module-kernel-features.csv.gz), and for each configuration it sums them over its closure together with
the number of modules with "Certificate" in the name and, where known, the closure's compile time (results/module-times.csv.gz).
It then ranks the features by rank correlation with the measured check time of the accepted configurations, fits
log10(check s) on log10(1 + feature) for the best few by least squares, reports the fit quality, and lists the predicted check time
for every configuration without an accepted check (with the fit's residual spread as the uncertainty). Association only, a small
number of heavy-tailed points: treat the ranking as a prioritisation hint, not a measurement.
Usage: nice -n 10 predict_check_cost.py
"""
import os, re, csv, gzip, json
import numpy as np
base = '/home/srv/s/math/openai-math'; root = base + '/src/lean'; table = base + '/results/module-kernel-features.csv.gz'
imp = re.compile(rb"^\s*(?:public\s+|meta\s+)*import\s+(?:public\s+|meta\s+)*(\S+)", re.M)
path = lambda m: os.path.join(root, *m.split('.')) + '.lean'
deps_cache, feats = {}, {}


def deps(m):
    if m not in deps_cache:
        try: src = open(path(m), 'rb').read()
        except OSError: deps_cache[m] = []; return []
        deps_cache[m] = [x.decode() for x in imp.findall(src) if x.decode().startswith(('OAI', 'ComparatorChallenges'))]
        if m not in feats: feats[m] = (len(src), src.count(b'decide +kernel'))
    return deps_cache[m]


def closure(roots):
    seen, todo = set(), list(roots)
    while todo:
        m = todo.pop()
        if m in seen: continue
        seen.add(m); todo += deps(m)
    return seen


cfgs = {}
for f in sorted(os.listdir(root + '/ComparatorChallenges')):
    if f.endswith('.json'): cfgs[f[:-5]] = json.load(open(f'{root}/ComparatorChallenges/{f}'))
mt = {r['module']: float(r['first_build_s']) for r in csv.DictReader(gzip.open(base + '/results/module-times.csv.gz', 'rt')) if r['likely_pause_artifact'] != '1'}
rows = {}
for n, c in cfgs.items():
    cl = closure([c['solution_module'], c['challenge_module']])
    fe = [feats.get(m, (0, 0)) for m in cl]
    rows[n] = dict(config=n, modules=len(cl), kb=sum(b for b, _ in fe) / 1024, decide_kernel=sum(k for _, k in fe),
                   certificate_modules=sum('Certificate' in m for m in cl), compile_h=sum(mt.get(m, 0) for m in cl) / 3600,
                   timed=sum(m in mt for m in cl) / max(1, len(cl)))
with gzip.open(table, 'wt', newline='') as f:
    w = csv.writer(f); w.writerow(['module', 'bytes', 'decide_kernel']); [w.writerow([m, *v]) for m, v in sorted(feats.items())]
cfg = {r['config']: r for r in csv.DictReader(open(base + '/results/cmp-all/configs.csv'))}
for n, r in rows.items():
    x = cfg.get(n, {}); r['check_s'] = float(x['check_active_s']) if x.get('status') == 'accepted' and x.get('check_active_s') else None
    r['status'] = x.get('status', '')
train = [r for r in rows.values() if r['check_s']]
FEATS = ['modules', 'kb', 'decide_kernel', 'certificate_modules', 'compile_h']


def ranks(v):
    o = np.argsort(v, kind='stable'); r = np.empty(len(v)); r[o] = np.arange(1, len(v) + 1)
    for x in set(v.tolist()):
        m = np.where(v == x)[0]
        if len(m) > 1: r[m] = r[m].mean()
    return r


y = np.log10([r['check_s'] for r in train])
print(f"{len(train)} configurations with a measured check; {len(rows) - len(train)} without")
print("rank correlation with check time:")
corr = {}
for k in FEATS:
    v = np.array([r[k] for r in train], float); corr[k] = float(np.corrcoef(ranks(v), ranks(np.array([r['check_s'] for r in train])))[0, 1]); print(f"  {k:20s} {corr[k]:6.2f}")
use = [k for k in FEATS if k != 'compile_h']          # compile time is missing for modules not yet built; keep the model to source-only features
X = np.column_stack([np.ones(len(train))] + [np.log10(1 + np.array([r[k] for r in train], float)) for k in use])
beta, *_ = np.linalg.lstsq(X, y, rcond=None); res = y - X @ beta; sd = res.std(); r2 = 1 - res.var() / y.var()
print(f"\nfit log10(check s) on log10(1+x) for {use}: R^2 {r2:.2f}, residual sd {sd:.2f} decades (about a factor {10 ** sd:.1f}); coefficients {np.round(beta, 2).tolist()}")
for r in rows.values():
    xv = np.array([1] + [np.log10(1 + r[k]) for k in use]); r['pred_s'] = float(10 ** (xv @ beta))
big = sorted(train, key=lambda r: -r['check_s'])[:8]
print("\nhow the fit does on the 8 slowest measured checks (measured / predicted s):")
for r in big: print(f"  {r['config']:28s} {r['check_s']:8.0f} / {r['pred_s']:8.0f}   decide+kernel {r['decide_kernel']:6d}  certificate modules {r['certificate_modules']:4d}")
pend = sorted([r for r in rows.values() if not r['check_s']], key=lambda r: -r['pred_s'])
print(f"\nconfigurations without an accepted check, by predicted check time (x/÷ {10 ** sd:.1f}):")
print(f"  {'config':30s} {'status':8s} {'pred s':>8s} {'modules':>7s} {'decide+kernel':>13s} {'cert mods':>9s}")
for r in pend[:20]: print(f"  {r['config']:30s} {r['status'] or 'pending':8s} {r['pred_s']:8.0f} {r['modules']:7d} {r['decide_kernel']:13d} {r['certificate_modules']:9d}")
out = base + '/results/check-cost-predictions.csv'
with open(out, 'w', newline='') as f:
    w = csv.DictWriter(f, ['config', 'status', 'check_s', 'pred_s', 'modules', 'kb', 'decide_kernel', 'certificate_modules', 'compile_h', 'timed'], extrasaction='ignore')
    w.writeheader(); [w.writerow({k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()}) for r in sorted(rows.values(), key=lambda r: -r['pred_s'])]
print(f"\nwrote {out}")
