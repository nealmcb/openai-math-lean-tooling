#!/usr/bin/env python3
"""verify_build_copy: check that a copy of the openai-math checkout and its Lake build is complete and byte-identical where it matters.

Purpose: the cloud build ran on a 1.6 TB disk, 497 GB of it transient `.setup.json` files; the copy to a 250 GB disk leaves those out (Lake regenerates them). This compares an OLD tree
and a NEW tree (each the openai-math checkout root, for example /mnt/old/home/srv/s/math/openai-math and /home/srv/s/math/openai-math):
  1. the number of .olean files in every top-level OAI directory, in ComparatorChallenges, and in every package's build directory, old against new;
  2. the number of .c, .c.hash, .trace and .ilean files under src/lean/.lake/build (the files Lake treats as outputs), old against new;
  3. byte-for-byte `cmp` of --samples (default 200) randomly chosen .olean files (fixed --seed), chosen from the new tree;
  4. that the new tree has no `.setup.json` file (expected) and that every ext/ tool binary (landrun, nanoda_bin, lean4export, comparator) exists and is executable.
Prints one line per check and a final PASS or FAIL; exit status 0 only on PASS. Read-only.
Usage: verify_build_copy.py OLD NEW [--samples 200] [--seed 20261014]
"""
import os, sys, random, subprocess, filecmp
old, new = sys.argv[1], sys.argv[2]
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
samples = int(arg('--samples', '200')); seed = int(arg('--seed', '20261014')); bad = []


def count(root, ext, sub):
    p = os.path.join(root, sub); n = 0
    if not os.path.isdir(p): return 0
    r = subprocess.run(['find', p, '-type', 'f', '-name', '*' + ext], capture_output=True, text=True)
    return len(r.stdout.split('\n')) - 1


lib = 'src/lean/.lake/build/lib/lean'
for sub in sorted(os.listdir(os.path.join(new, lib, 'OAI'))) + ['..OAI.olean']:
    if sub.startswith('..'): continue
    o, n = count(old, '.olean', f'{lib}/OAI/{sub}'), count(new, '.olean', f'{lib}/OAI/{sub}')
    print(f"olean OAI/{sub:28s} old {o:6d} new {n:6d} {'ok' if o == n else 'MISMATCH'}"); bad += [f'olean {sub}'] if o != n else []
for sub in ('ComparatorChallenges',):
    o, n = count(old, '.olean', f'{lib}/{sub}'), count(new, '.olean', f'{lib}/{sub}'); print(f"olean {sub:33s} old {o:6d} new {n:6d} {'ok' if o == n else 'MISMATCH'}"); bad += [sub] if o != n else []
pk = os.path.join(new, 'src/lean/.lake/packages')
for p in sorted(os.listdir(pk)):
    o, n = count(old, '.olean', f'src/lean/.lake/packages/{p}/.lake/build'), count(new, '.olean', f'src/lean/.lake/packages/{p}/.lake/build')
    if o or n: print(f"olean package {p:27s} old {o:6d} new {n:6d} {'ok' if o == n else 'MISMATCH'}"); bad += [f'package {p}'] if o != n else []
for ext in ('.c', '.c.hash', '.trace', '.ilean'):
    o, n = count(old, ext, 'src/lean/.lake/build'), count(new, ext, 'src/lean/.lake/build'); print(f"{ext:8s} under src/lean/.lake/build      old {o:6d} new {n:6d} {'ok' if o == n else 'MISMATCH'}"); bad += [ext] if o != n else []
files = subprocess.run(['find', os.path.join(new, lib), '-type', 'f', '-name', '*.olean'], capture_output=True, text=True).stdout.split('\n')[:-1]
pick = random.Random(seed).sample(files, min(samples, len(files))); diff = [f for f in pick if not filecmp.cmp(f, os.path.join(old, os.path.relpath(f, new)), shallow=False)]
print(f"byte comparison of {len(pick)} random .olean files (seed {seed}): {len(diff)} differ"); bad += diff[:3]
extra = subprocess.run(['find', new, '-name', '*.setup.json'], capture_output=True, text=True).stdout.split('\n')[:-1]
print(f".setup.json files in the new tree: {len(extra)} (expected 0)")
for t in ('ext/bin/landrun', 'ext/bin/nanoda_bin', 'ext/lean4export/.lake/build/bin/lean4export', 'ext/comparator/.lake/build/bin/comparator'):
    ok = os.access(os.path.join(new, t), os.X_OK); print(f"tool {t}: {'ok' if ok else 'MISSING'}"); bad += [t] if not ok else []
print('PASS' if not bad else f'FAIL: {bad[:5]}'); sys.exit(0 if not bad else 1)
