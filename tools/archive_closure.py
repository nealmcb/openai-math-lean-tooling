#!/usr/bin/env python3
"""archive_closure: compress (verify, then remove) the generated C files for the import closure of the given configs.

Purpose: free disk after a config's Comparator check, touching only that config's own files (safe while other
builds run in the same workspace, unlike directory-wide tools/archive_ir.sh). Files also needed by --keep configs stay.
Restore later with tools/restore_ir_for.py (it reads every archive/*.tar.zst).
Usage: archive_closure.py LEAN_ROOT CONFIG [CONFIG...] [--keep CONFIG...]
"""
import sys, os, re, json, subprocess, time
root = sys.argv[1]; args = sys.argv[2:]
keep_i = args.index('--keep') if '--keep' in args else len(args)
names, keepn = args[:keep_i], args[keep_i + 1:]
base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')); bld = root + '/.lake/build'
imp = re.compile(rb"^\s*(?:public\s+|meta\s+)*import\s+(?:public\s+|meta\s+)*(\S+)", re.M)
def clos(cfgs):
    seen, todo = set(), []
    for n in cfgs:
        c = json.load(open(f'{root}/ComparatorChallenges/{n}.json')); todo += [c['solution_module'], c['challenge_module']]
    while todo:
        m = todo.pop(); p = os.path.join(root, *m.split('.')) + '.lean'
        if m in seen or not os.path.exists(p): continue
        seen.add(m); todo += [x.decode() for x in imp.findall(open(p, 'rb').read())]
    return seen
mods = clos(names) - clos(keepn)
files = []
for m in mods:
    st = 'ir/' + '/'.join(m.split('.'))
    files += [f for f in (st + '.c', st + '.c.hash', st + '.setup.json') if os.path.exists(f'{bld}/{f}')]
if not files: print('nothing to archive'); sys.exit(0)
lst = f'{base}/scratch/archive-closure-{os.getpid()}.lst'; open(lst, 'w').write('\n'.join(files) + '\n')
out = f'{base}/archive/cfg-{"+".join(names)[:60]}-{int(time.time())}.tar.zst'; os.makedirs(base + '/archive', exist_ok=True)
p = subprocess.run(f'nice -n 10 tar -C {bld} -cf - --files-from {lst} | zstd -T4 -3 -q -o {out}', shell=True)
t = subprocess.run(['zstd', '-tq', out])
if p.returncode == 0 and t.returncode == 0:
    sz = sum(os.path.getsize(f'{bld}/{f}') for f in files)
    for f in files: os.remove(f'{bld}/{f}')
    print(f'archived {len(files)} files, {sz/2**30:.1f} GiB -> {os.path.getsize(out)/2**20:.0f} MiB: {out}')
else: print('ARCHIVE FAILED; originals kept')
os.unlink(lst)
