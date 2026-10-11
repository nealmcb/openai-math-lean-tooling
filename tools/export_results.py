#!/usr/bin/env python3
"""export_results: one CSV row per Comparator config (all 416), joining every result source.

Purpose: a single reviewable table of per-config observations: closure size, predicted vs measured peak VMAs, build and check
wall time, memory, outcome, nanoda use. Sources: results/cmp-all/all.jsonl (check records; for batched builds the build time
is the batch's, from batches.jsonl, shared by the configs in that batch), results/config-solution-size.json,
results/predicted-vmas.jsonl, ComparatorChallenges/*.json. Configs not yet attempted appear with status 'pending'.
build_wall_s is the time of the build STEP: near zero when the config's modules were already compiled for an earlier config or batch, and shared by every config in a batch
(see build_scope and modules_compiled_in_this_build); it is not additive across configs.
Writes /home/srv/s/math/openai-math/results/cmp-all/configs.csv and prints a summary.
Usage: export_results.py
"""
import json, csv, os, glob
base = '/home/srv/s/math/openai-math'; R = base + '/results/cmp-all'; root = base + '/src/lean'
size = {n: (sz, s) for sz, n, s in json.load(open(base + '/results/config-solution-size.json'))}
pred = {}
for l in open(base + '/results/predicted-vmas.jsonl'):
    d = json.loads(l); pred[d['module']] = d
order = json.load(open(base + '/results/config-order.json')); pos = {n: i + 1 for i, n in enumerate(order)}
batches = {}
if os.path.exists(R + '/batches.jsonl'):
    for l in open(R + '/batches.jsonl'):
        d = json.loads(l); batches[str(d['batch'])] = d
rec = {}
for l in open(R + '/all.jsonl'):
    d = json.loads(l); rec[d['config']] = d            # last record per config wins
rows = []
for n, (cl, sol) in size.items():
    cfg = json.load(open(f'{root}/ComparatorChallenges/{n}.json')); d = rec.get(n, {}); p = pred.get(sol, {})
    b = batches.get(str(d.get('batch', '')).split('-')[0], {}) if d.get('build_skipped') else {}
    bad = isinstance(d.get('peak_vmas'), (int, float)) and d['peak_vmas'] < 1000      # early records: monitor saw only the sandbox wrapper
    if bad: d = dict(d, peak_vmas=None, peak_rss_gib=None)
    rows.append(dict(
        config=n, status=d.get('outcome', 'pending'), solution_module=sol, in_repo_closure=cl,
        predicted_vmas=p.get('predicted_vmas'), measured_check_peak_vmas=d.get('peak_vmas'),
        measured_build_peak_vmas=d.get('build_peak_vmas') or b.get('peak_vmas'),
        build_wall_s=d.get('build_s') if d.get('build_s') is not None else b.get('build_wall_s'),
        batch_configs=(len(b.get('configs', [])) if d.get('build_skipped') else 1),
        modules_compiled_in_this_build=(d.get('modules_built_this_run') if not d.get('build_skipped') else b.get('modules_built')),
        build_scope='this config' if not d.get('build_skipped') else f"batch {d.get('batch')} (shared by {len(b.get('configs', []))} configs)" if b else ('seeded from pilot' if 'seeded_from' in d else ''),
        check_wall_s=d.get('cmp_s'), check_peak_rss_gib=d.get('peak_rss_gib'), nanoda=cfg.get('enable_nanoda'),
        theorems=len(cfg.get('theorem_names', [])), solution_lines=d.get('solution_lines'), order_position=pos.get(n),
        started=d.get('started'), detail=d.get('detail', '') or ('check memory/VMA monitor invalid for this early record (saw only the sandbox wrapper)' if bad else '')))
for r in rows:
    bw, n = r['build_wall_s'], r['batch_configs']
    r['build_share_s'] = round(float(bw) / n, 1) if bw not in (None, '') and n else ''
cols = list(rows[0]); out = R + '/configs.csv'
with open(out, 'w', newline='') as f:
    w = csv.DictWriter(f, cols); w.writeheader(); w.writerows(rows)
done = [r for r in rows if r['status'] == 'accepted']
print(f"wrote {out}: {len(rows)} configs, {len(done)} accepted, {sum(r['status'] == 'pending' for r in rows)} pending, "
      f"{sum(r['status'] not in ('accepted', 'pending') for r in rows)} other")
print(f"{'config':32s} {'closure':>7s} {'pred':>6s} {'meas':>6s} {'build_s':>8s} {'check_s':>8s} {'GiB':>5s}")
for r in sorted(done, key=lambda r: -(r['check_wall_s'] or 0))[:25]:
    f = lambda v, fmt: format(v, fmt) if isinstance(v, (int, float)) else '-'
    print(f"{r['config']:32s} {r['in_repo_closure']:7d} {f(r['predicted_vmas'], '6d')} {f(r['measured_check_peak_vmas'], '6.0f')} {f(r['build_wall_s'], '8.0f')} {f(r['check_wall_s'], '8.0f')} {f(r['check_peak_rss_gib'], '5.1f')}")
