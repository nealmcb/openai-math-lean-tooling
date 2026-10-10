#!/usr/bin/env python3
"""restore_ir_for: restore archived generated-C files needed by one Comparator config's modules.

Purpose: tools/archive_ir.sh compresses lake's build/ir C output to free disk. If a later `lake build` needs a module
whose C file was archived, Lake would recompile it (slow). This extracts only the files for the config's solution and
challenge import closure (X.c, X.c.hash, X.setup.json) from every archive/*.tar.zst, so Lake sees them up to date.
Usage: restore_ir_for.py LEAN_ROOT CONFIG_NAME   (prints how many files were restored)
"""
import sys, os, re, glob, subprocess, json, tempfile
root, name = sys.argv[1:3]
base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
imp = re.compile(rb"^\s*(?:public\s+|meta\s+)*import\s+(?:public\s+|meta\s+)*(\S+)", re.M)
cfg = json.load(open(os.path.join(root, f'ComparatorChallenges/{name}.json')))
seen, todo = set(), [cfg['solution_module'], cfg['challenge_module']]
while todo:
    m = todo.pop()
    p = os.path.join(root, *m.split('.')) + '.lean'
    if m in seen or not os.path.exists(p): continue
    seen.add(m)
    todo += [x.decode() for x in imp.findall(open(p, 'rb').read())]
need = []
for m in seen:
    stem = 'ir/' + '/'.join(m.split('.'))
    if os.path.exists(os.path.join(root, '.lake/build', stem + '.c')): continue      # already present
    need += [stem + '.c', stem + '.c.hash', stem + '.setup.json']
if not need:
    print('restored 0 (nothing missing)'); sys.exit(0)
with tempfile.NamedTemporaryFile('w', suffix='.lst', delete=False) as f:
    f.write('\n'.join(need) + '\n'); lst = f.name
n0 = sum(os.path.exists(os.path.join(root, '.lake/build', p)) for p in need)
for arch in sorted(glob.glob(os.path.join(base, 'archive', '*.tar.zst'))):
    subprocess.run(['tar', '--zstd', '-xf', arch, '-C', os.path.join(root, '.lake/build'), '--files-from', lst, '--ignore-failed-read'],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
n1 = sum(os.path.exists(os.path.join(root, '.lake/build', p)) for p in need)
print(f'restored {n1 - n0} files for {len(seen)} modules')
os.unlink(lst)
