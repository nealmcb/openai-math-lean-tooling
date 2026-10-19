#!/usr/bin/env python3
"""restore_ir_for: restore generated-C files needed by one Comparator config's modules.

Purpose: tools/archive_ir.sh compresses lake's build/ir C output to free disk. If a later `lake build` needs a module
whose C file was archived, Lake would recompile it (slow). This extracts only the files for the config's solution and
challenge import closure (X.c, X.c.hash, X.setup.json) from every archive/*.tar.zst, so Lake sees them up to date.
Sources, in order: archive/*.tar.zst; then, with --from-cache, `lake build` of the OAI modules still missing, which restores
their complete outputs (.olean, .ilean, .c, trace) from the published Lake cache, so the archives are not needed for them.
That needs a cache service in the Lake configuration (see results/lake-cache-test/README.md, "Quick use"). Prints what was
restored and how many modules are still without a C file.
Usage: restore_ir_for.py LEAN_ROOT CONFIG_NAME [--from-cache]
"""
import sys, os, re, glob, subprocess, json, tempfile
root, name = sys.argv[1:3]; from_cache = '--from-cache' in sys.argv
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
for m in sorted(seen):
    if not m.startswith(('OAI', 'ComparatorChallenges')): continue      # dependency packages keep their own build dirs
    stem = 'ir/' + '/'.join(m.split('.'))
    if os.path.exists(os.path.join(root, '.lake/build', stem + '.c')): continue      # already present
    need += [stem + '.c', stem + '.c.hash', stem + '.setup.json']
if not need:
    print('restored 0 (nothing missing)'); sys.exit(0)
with tempfile.NamedTemporaryFile('w', suffix='.lst', delete=False) as f:
    f.write('\n'.join(need) + '\n'); lst = f.name
n0 = sum(os.path.exists(os.path.join(root, '.lake/build', p)) for p in need)
os.makedirs(os.path.join(root, '.lake/build'), exist_ok=True)
tarballs = sorted(glob.glob(os.path.join(base, 'archive', '*.tar.zst')))
for arch in tarballs:
    subprocess.run(['tar', '--zstd', '-xf', arch, '-C', os.path.join(root, '.lake/build'), '--files-from', lst, '--ignore-failed-read'],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
os.unlink(lst)
have = lambda p: os.path.exists(os.path.join(root, '.lake/build', p))
n1 = sum(have(p) for p in need)
missing = sorted(m for m in seen if m.startswith('OAI.') and not have('ir/' + '/'.join(m.split('.')) + '.c'))
if from_cache and missing:
    env = dict(os.environ, LAKE_ARTIFACT_CACHE='true', LAKE_RESTORE_ARTIFACTS='true')   # copy the outputs into .lake/build, do not just reference the cache
    r = subprocess.run(['lake', 'build'] + missing, cwd=root, env=env, capture_output=True, text=True)
    print(f'lake build of {len(missing)} missing OAI modules from the cache: exit {r.returncode}; {r.stdout.strip().splitlines()[-1:] if r.stdout.strip() else r.stderr.strip().splitlines()[-1:]}')
    n1 = sum(have(p) for p in need)
nomod = sum(not have('ir/' + '/'.join(m.split('.')) + '.c') for m in seen if m.startswith(('OAI', 'ComparatorChallenges')))
print(f'restored {n1 - n0} files for {len(seen)} modules; {nomod} modules still without a C file')
