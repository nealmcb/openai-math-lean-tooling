#!/usr/bin/env python3
"""export_module_times: one row per module with its recorded build time, from the raw Lake build logs.

Purpose: per-module data behind the aggregate numbers. Lake prints "Built <module> (<time>)" when it compiles a module; the
raw logs are too bulky for git, so this extracts them. Columns: module, area (first two name components), first_build_s (the earliest recorded compile, by log
file modification time), n_builds (more than 1 when a module was recompiled, e.g. after its generated C was archived or
a run was interrupted), source_bytes, in_repo_closure, predicted_vmas (40 + 5*M + O from tools/predict_vmas.py).
likely_pause_artifact marks the 16 modules whose time falls in 1370-1410 s, the length of the 1377 s manual pause of 10:46-11:09 in driver.log
(they were mid-compile when the run was paused); shorter pauses left less visible traces that cannot be separated from real durations.
Times are wall-clock under load (other modules compiling at once, a thermally limited laptop, some paused periods), so they
are upper bounds on isolated compile time. Modules never compiled in a logged run have no row ("replayed" means cached).
Writes results/module-times.csv.gz.  Usage: export_module_times.py
"""
import re, glob, os, csv, gzip, json
base = '/home/srv/s/math/openai-math'; root = base + '/src/lean'
secs = lambda s: sum(float(n) * {'ms': .001, 's': 1, 'm': 60, 'h': 3600}[u] for n, u in re.findall(r'([\d.]+)(ms|s|m|h)', s))
logs = sorted(glob.glob(base + '/results/**/*.log', recursive=True), key=os.path.getmtime)
first, count = {}, {}
for f in logs:
    for m, t in re.findall(r'Built (\S+) \(([^)]*)\)', open(f, errors='replace').read()):
        count[m] = count.get(m, 0) + 1
        first.setdefault(m, secs(t))
clos = {}
for fn in ('oai-closure-sizes.jsonl', 'solution-closure-sizes.jsonl'):
    for l in open(f'{base}/results/{fn}'):
        d = json.loads(l); clos.setdefault(d['module'], d['in_repo_closure'])
pred = {}
for l in open(base + '/results/predicted-vmas.jsonl'):
    d = json.loads(l); pred[d['module']] = d['predicted_vmas']
n = 0
with gzip.open(base + '/results/module-times.csv.gz', 'wt', newline='') as f:
    w = csv.writer(f); w.writerow(['module', 'area', 'likely_pause_artifact', 'first_build_s', 'n_builds', 'source_bytes', 'in_repo_closure', 'predicted_vmas'])
    for m in sorted(first):
        p = os.path.join(root, *m.split('.')) + '.lean'
        w.writerow([m, '.'.join(m.split('.')[:2]), int(1370 <= first[m] < 1410), round(first[m], 1), count[m], os.path.getsize(p) if os.path.exists(p) else '', clos.get(m, ''), pred.get(m, '')]); n += 1
print(f'wrote results/module-times.csv.gz: {n} modules, {sum(1 for m in count if count[m] > 1)} compiled more than once')
