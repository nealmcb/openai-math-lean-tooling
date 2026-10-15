#!/usr/bin/env python3
"""cpu_hours_estimate: rough CPU-hours for verifying the whole library with Lean's kernel and with nanoda, from the recorded measurements.

Purpose: REPORT.md section 1a asks what the whole job costs in CPU time under the two pipelines. Both start from the same build (every OAI module compiled once);
they differ in two places: Lean's pipeline keeps the kernel check inside the compile and adds Comparator's Lean replay of each of the 416 exports; the nanoda pipeline compiles with
`debug.skipKernelTC=true` (the compile CPU falls by the share measured in results/skip-kernel-test/sample.jsonl), exports each solution (single-threaded lean4export) and checks the export with
nanoda (CPU time of the run), and also covers the modules no solution imports (results/uncovered/full.jsonl). Inputs and how each number is formed:
  * compile CPU: the 26-module sample (normal compile CPU per laptop first-build second, by stratum) weighted by each stratum's share of results/module-times.csv.gz (79,201 timed modules),
    scaled to all 122,458 modules by module count; this is a laptop-equivalent figure (i5-1340P), the cloud CPUs differ;
  * skip-kernel saving: weighted CPU saving of the same sample;
  * Lean checks: results/cmp-all/configs.csv check_active_s (the export, Lean's replay and start-up are single-threaded, so CPU is close to the active wall time);
  * nanoda checks: results/kernel-pair-sweep.jsonl (export seconds plus nanoda CPU seconds, 390 configurations), results/long-nanoda/ (18 long configurations), PlanarPacking from
    results/nanoda-scaling-cloud (export plus 39,559 s of declaration work), and the three configurations that do not finish (not counted: no verdict);
  * modules no solution imports: results/uncovered/full.jsonl (export seconds plus nanoda CPU seconds).
Writes results/cpu-hours-estimate.json and prints a table. A rough estimate: it ignores Lake start-up, the idle tails, and I/O waits.
Usage: cpu_hours_estimate.py
"""
import json, csv, gzip, os, collections
base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')); R = base + '/results'
H = 3600.0
# --- compile CPU
mt = [(float(r['first_build_s'])) for r in csv.DictReader(gzip.open(R + '/module-times.csv.gz', 'rt')) if r['first_build_s']]
edges = [0, 5, 20, 60, 200, 1e9]; stratum = lambda s: next(i for i in range(5) if edges[i] <= s < edges[i + 1])
W = collections.Counter(); N = collections.Counter()
for s in mt: W[stratum(s)] += s; N[stratum(s)] += 1
samp = [json.loads(l) for l in open(R + '/skip-kernel-test/sample.jsonl') if l.strip().startswith('{')]
rho = {}; save = {}
for st in range(5):
    m = [x for x in samp if x['stratum'] == st]
    if not m: continue
    lap = sum(x['laptop_s'] for x in m); cn = sum(x['normal'][2] for x in m); cs = sum(x['skip'][2] for x in m)
    rho[st] = cn / lap; save[st] = 1 - cs / cn
timed_cpu = sum(W[st] * rho[st] for st in rho); saved = sum(W[st] * rho[st] * save[st] for st in rho)
scale = 122458 / len(mt)
compile_cpu_h = timed_cpu * scale / H; skip_saving = saved / timed_cpu
# --- Lean checks
cfg = list(csv.DictReader(open(R + '/cmp-all/configs.csv')))
lean_check_h = sum(float(r['check_active_s']) for r in cfg if r['check_active_s']) / H
# --- nanoda checks
sw = [json.loads(l) for l in open(R + '/kernel-pair-sweep.jsonl')]
sweep_ok = [x for x in sw if x.get('nanoda_rc') == 0]
sweep_export = sum(x['export_s'] for x in sweep_ok); sweep_nano = sum(x['nanoda_cpu_s'] for x in sweep_ok if x.get('nanoda_cpu_s'))
sweep_lean_replay = sum((x['lean_cpu_s'] or 0) for x in sweep_ok)
ex, run = {}, {}
for l in open(R + '/long-nanoda/nanoda-scaling.jsonl'):
    d = json.loads(l)
    if 'threads' in d: run[d['config']] = d
    elif 'export_s' in d: ex[d['config']] = d['export_s']
long_ok = [c for c, d in run.items() if d['exit'] == 0]
long_export = sum(ex.get(c, 0) for c in long_ok); long_nano = sum(run[c]['cpu_s'] for c in long_ok)
planar = 840 + 39559
unc = [json.loads(l) for l in open(R + '/uncovered/full.jsonl')]
unc_ok = [x for x in unc if x.get('nanoda_rc') == 0]
unc_export = sum(x['export_s'] for x in unc_ok); unc_nano = sum(x['nanoda_cpu_s'] for x in unc_ok)
out = dict(
    compile_cpu_h_all_modules=round(compile_cpu_h, 1), skip_kernel_cpu_saving=round(skip_saving, 3), compile_cpu_h_skipkernel=round(compile_cpu_h * (1 - skip_saving), 1),
    lean_comparator_checks_h=round(lean_check_h, 1),
    nanoda_sweep=dict(configs=len(sweep_ok), export_h=round(sweep_export / H, 1), nanoda_cpu_h=round(sweep_nano / H, 1), lean_replay_cpu_h_same_configs=round(sweep_lean_replay / H, 1)),
    nanoda_long=dict(configs=len(long_ok), export_h=round(long_export / H, 1), nanoda_cpu_h=round(long_nano / H, 1)),
    nanoda_planarpacking_h=round(planar / H, 1),
    nanoda_uncovered=dict(pieces=len(unc_ok), export_h=round(unc_export / H, 1), nanoda_cpu_h=round(unc_nano / H, 1)))
nano_checks = (sweep_export + sweep_nano + long_export + long_nano + planar) / H
out['nanoda_checks_416_h'] = round(nano_checks, 1); out['nanoda_uncovered_h'] = round((unc_export + unc_nano) / H, 1)
out['total_lean_h'] = round(compile_cpu_h + lean_check_h, 1)
out['total_nanoda_h_416_only'] = round(compile_cpu_h * (1 - skip_saving) + nano_checks, 1)
out['total_nanoda_h_with_uncovered'] = round(out['total_nanoda_h_416_only'] + out['nanoda_uncovered_h'], 1)
json.dump(out, open(R + '/cpu-hours-estimate.json', 'w'), indent=1)
print(json.dumps(out, indent=1))

# --- table of the long configurations (laptop Lean check against export plus nanoda on the cloud machine), for REPORT.md
lap = {r['config']: float(r['check_active_s']) for r in cfg if r['check_active_s']}
rows = ['| Configuration | Laptop check (Lean) | Export | nanoda, 8 threads | Export + nanoda | Speed-up | Peak memory |', '|---|---|---|---|---|---|---|']
for c in sorted(run, key=lambda c: -lap[c]):
    d = run[c]; e = ex.get(c)
    if d['exit'] == 0:
        t = e + d['wall_s']; rows.append(f"| {c} | {lap[c]:,.0f} s | {e:,.0f} s | {d['wall_s']:,.0f} s | {t:,.0f} s | {lap[c] / t:.1f}x | {d['rss_gib']:.1f} GiB |")
    else:
        reached = {'Laughlin': 151, 'LaughlinFock': 127, 'LaughlinPlanar': 175}.get(c, 0)   # GiB observed before the process died or was suspended
        rows.append(f"| {c} | {lap[c]:,.0f} s | {e:,.0f} s | did not finish | | | {reached} GiB when it ended |")
open(R + '/long-nanoda/table.md', 'w').write('\n'.join(rows) + '\n')
