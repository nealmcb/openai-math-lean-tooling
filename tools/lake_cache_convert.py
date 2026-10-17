#!/usr/bin/env python3
"""lake_cache_convert: turn a fully built openai/math workspace into a Lake artifact cache: one .ltar bundle per module plus one mapping file.

Purpose: publish the compiled OAI library as a per-module Lake cache (see results/lake-cache-test/README.md for the consumer side). On an up-to-date workspace `lake build MODULES -o map.jsonl` with
LAKE_ARTIFACT_CACHE=true compiles nothing; it only bundles the outputs into LAKE_CACHE_DIR/artifacts/<hash>.ltar and writes the mapping (input hash -> bundle) to map.jsonl. This driver splits the modules
of OAI/ by top-level area into --procs groups of about equal size (largest first), runs one lake process per group concurrently with a shared cache dir (measured: safe, 0 conflicting keys), then builds the
root module OAI last, and merges all mapping files into OUT/map-all.jsonl (header line, then unique [inputHash, "<hash>.ltar"] lines). Lake also copies the dependency (Mathlib) outputs into the cache dir (about 8 GB);
only the bundles named in the merged mapping are meant to be published.
Usage: lake_cache_convert.py WORKSPACE OUT [--procs 4]   (OUT/cache is the cache dir; logs and per-group maps in OUT/; run with lake on PATH; resumable, rerun converts what is missing quickly)
"""
import os, sys, json, subprocess, time, glob
ws, out = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]); procs = int(sys.argv[sys.argv.index('--procs') + 1]) if '--procs' in sys.argv else 4
os.makedirs(os.path.join(out, 'cache'), exist_ok=True)
env = dict(os.environ, LAKE_ARTIFACT_CACHE='true', LAKE_CACHE_DIR=os.path.join(out, 'cache'))
areas = {}
for a in sorted(os.listdir(os.path.join(ws, 'OAI'))):
    p = os.path.join(ws, 'OAI', a)
    mods = []
    if os.path.isdir(p):
        for dp, dn, fn in os.walk(p): mods += ['OAI.' + os.path.relpath(os.path.join(dp, f[:-5]), os.path.join(ws, 'OAI')).replace('/', '.') for f in fn if f.endswith('.lean')]
    elif a.endswith('.lean'): mods = ['OAI.' + a[:-5]]
    areas[a] = mods
groups = [[] for _ in range(procs)]
for a, mods in sorted(areas.items(), key=lambda kv: -len(kv[1])): min(groups, key=lambda g: len(g)).extend(mods)
print(f"{sum(len(m) for m in areas.values())} modules in {len(areas)} areas; group sizes {[len(g) for g in groups]}", flush=True)
t0 = time.time(); running = []
for i, g in enumerate(groups):
    lst = os.path.join(out, f'group{i}.txt'); open(lst, 'w').write('\n'.join(g) + '\n')
    cmd = f'/usr/bin/time -f "%e s %P cpu %M KB" -o {out}/group{i}.time lake build $(cat {lst} | tr "\\n" " ") -o {out}/map-{i}.jsonl > {out}/group{i}.log 2>&1'
    running.append(subprocess.Popen(cmd, shell=True, cwd=ws, env=env))
rc = [p.wait() for p in running]; print(f"groups finished in {time.time() - t0:.0f} s, exit codes {rc}", flush=True)
cmd = f'lake build OAI -o {out}/map-root.jsonl > {out}/root.log 2>&1'; rc_root = subprocess.run(cmd, shell=True, cwd=ws, env=env).returncode
print(f"root OAI exit {rc_root}, total {time.time() - t0:.0f} s", flush=True)
merged = {}; conflicts = 0
for f in sorted(glob.glob(os.path.join(out, 'map-[0-9r]*.jsonl'))):
    for l in open(f):
        if l.startswith('['):
            k, v = json.loads(l)
            if merged.setdefault(k, v) != v: conflicts += 1
with open(os.path.join(out, 'map-all.jsonl'), 'w') as f:
    f.write('"2026-03-17"\n')
    for k, v in merged.items(): f.write(json.dumps([k, v]) + '\n')
print(f"merged {len(merged)} keys, {conflicts} conflicts; compiled lines: {sum(open(p).read().count('Compiling') for p in glob.glob(os.path.join(out, '*.log')))}", flush=True)
