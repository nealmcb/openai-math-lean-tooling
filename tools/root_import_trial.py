#!/usr/bin/env python3
"""root_import_trial: import every built module of OAI.lean's closure into one Lean process, at the current vm.max_map_count.

Purpose: `import OAI` cannot be tried directly while some of its 91,762 modules are unbuilt (OAI.olean itself does not exist).
This writes scratch/RootImportTrial.lean with `import Mathlib` plus one `import` line for every module reachable from OAI.lean that
has an .olean (results/oai-closure-sizes.jsonl, minus OAI itself), runs it with `lake env lean` under tools/vmamon.py, and prints the
outcome: exit code, the first error line, wall time, peak per-process mappings and vmamon's classification. At the default limit of
65,530 the process is expected to fail with "failed to read file ... .olean" once the mappings run out; run it under
tools/with_maxmap.sh N to try a raised limit. Output goes to results/root-import-trial/LIMIT/. Refuses to run at a limit it was
not asked about: pass --expect-limit N (default 65530) so a stale sysctl cannot be mistaken for the default.
With --root it instead runs the real root module src/lean/OAI.lean (its 914 `import` lines, in the repository's own order), so that
the first module that is not built is what stops it once the mapping limit is out of the way.
Usage: root_import_trial.py [--expect-limit 65530] [--root]
"""
import json, os, re, subprocess, sys, time
base = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')); root = base + '/src/lean'; lib = root + '/.lake/build/lib/lean'
want = int(sys.argv[sys.argv.index('--expect-limit') + 1]) if '--expect-limit' in sys.argv else 65530
have = int(open('/proc/sys/vm/max_map_count').read())
if have != want: sys.exit(f"vm.max_map_count is {have}, expected {want}; refusing to run")
mods = [json.loads(l)['module'] for l in open(base + '/results/oai-closure-sizes.jsonl')]
built = [m for m in mods if m != 'OAI' and os.path.exists(os.path.join(lib, *m.split('.')) + '.olean')]
os.makedirs(base + '/scratch', exist_ok=True); f = base + '/scratch/RootImportTrial.lean'
ROOT = '--root' in sys.argv
if ROOT: f = root + '/OAI.lean'
else: open(f, 'w').write('import Mathlib\n' + '\n'.join('import ' + m for m in built) + '\n')
out = f'{base}/results/root-import-trial/{have}' + ('-root' if ROOT else ''); os.makedirs(out, exist_ok=True)
t0 = time.time()
r = subprocess.run(['python3', '-I', base + '/tools/vmamon.py', '--out', out, '--interval', '0.05', '--label', f'root-import-{have}', '--', 'lake', 'env', 'lean', f], cwd=root, capture_output=True, text=True)
s = json.load(open(out + '/summary.json')); log = open(out + '/stdout.log', errors='replace').read()
err = [l for l in log.splitlines() if 'error' in l.lower()][:1]
print(f"limit {have}: " + ('the real OAI.lean' if ROOT else f"imported {len(built)} OAI modules (of {len(mods)} reachable from OAI.lean) plus Mathlib"))
print(f"exit {s['exit_code']}, wall {s['wall_s']:.1f} s, peak per-process mappings sampled {s['peak_per_process_vmas_sampled']}, class: {s['classification']}")
print('first error:', err[0][:300] if err else '(none)')
