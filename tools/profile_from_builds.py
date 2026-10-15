#!/usr/bin/env python3
"""profile_from_builds: per-module profiler breakdown (kernel "type checking" and the other categories) from the build logs of a cloud run.

Purpose: from 2026-10-14 15:04 MDT the cloud builds run every `lean` with `-D profiler=true -D profiler.threshold=100000` (set in the throttle wrapper
ext/sysroot-throttled/bin/lean; the threshold hides the per-declaration lines, so only the end-of-module "cumulative profiling times" block is printed). Lake keeps
that block in the module's log and prints it after the line "ℹ [n/m] Built MODULE (Ts)". This reads results/cmp-all/builds/*.log (the cloud run's per-build logs) and writes one
CSV row per module with the build time and the milliseconds in each profiler category: type checking is Lean's kernel checking the declarations as they are
added (it does not include kernel work done inside `decide +kernel`, which is counted under other categories), `blocked (unaccounted)` is thread waiting time and is not CPU.
A module built by more than one build log (shared dependencies) appears once, from the first log that has it. Usage: profile_from_builds.py LOGDIR [OUT.csv]
"""
import sys, os, re, csv, glob
logdir = sys.argv[1]; out = sys.argv[2] if len(sys.argv) > 2 else 'profile-by-module.csv'
built = re.compile(r'^[ℹ✔⚠✖]\s*\[\d+/\d+\] Built (\S+) \(([\d.]+)(ms|s)\)')
cat = re.compile(r'^\t(.+?) ([\d.]+)(µs|ms|s|us|min)$')
unit = {'us': 1e-3, 'µs': 1e-3, 'ms': 1.0, 's': 1000.0, 'min': 60000.0}
rows = {}; cats = set()
for path in sorted(glob.glob(os.path.join(logdir, '*.log'))):
    cur = None; inprof = False
    for line in open(path, errors='replace'):
        m = built.match(line)
        if m:
            cur = m.group(1); inprof = False
            if cur not in rows: rows[cur] = {'module': cur, 'built_s': float(m.group(2)) * (0.001 if m.group(3) == 'ms' else 1)}; fresh = True
            else: fresh = False
            continue
        if 'cumulative profiling times' in line: inprof = True; continue
        if inprof and cur and fresh:
            c = cat.match(line.rstrip('\n'))
            if c: rows[cur][c.group(1)] = float(c.group(2)) * unit[c.group(3)]; cats.add(c.group(1))
            elif not line.startswith('\t'): inprof = False
cols = ['module', 'built_s'] + sorted(cats)
with open(out, 'w', newline='') as f:
    w = csv.DictWriter(f, cols, restval=''); w.writeheader(); [w.writerow(r) for r in rows.values() if len(r) > 2]
prof = [r for r in rows.values() if 'type checking' in r]
tk = sum(r['type checking'] for r in prof) / 1000; tb = sum(r['built_s'] for r in prof)
print(f"{len(rows)} modules in the logs, {len(prof)} with a profile; kernel type checking {tk:.0f} s of {tb:.0f} s build time ({100 * tk / max(tb, 1):.1f}%); written {out}")
