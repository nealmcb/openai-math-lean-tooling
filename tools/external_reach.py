#!/usr/bin/env python3
"""external_reach: which fraction of each dependency package (Mathlib, ...) is transitively imported by this project.

Purpose: answer "how much of the Lean library ecosystem does the OAI work actually rely on?"
Parses `import` lines of every project .lean file (OAI/, ComparatorChallenges/), resolves each module name to a
package under .lake/packages/<pkg>/ or the Lean toolchain's src/lean, follows imports transitively through them,
and reports reached/total module counts per package. Source-text based; ignores `import` inside comments (rare).
Usage: external_reach.py LEAN_ROOT TOOLCHAIN_SRC_DIR
"""
import sys, os, re, collections
root, tc = sys.argv[1], sys.argv[2]
imp = re.compile(rb"^\s*(?:public\s+|meta\s+)*import\s+(?:public\s+|meta\s+)*(\S+)", re.M)
pk = os.path.join(root, '.lake/packages')
srcroots = {p: os.path.join(pk, p) for p in os.listdir(pk)}
srcroots['<lean-core>'] = tc
def find(mod):
    rel = os.path.join(*mod.split('.')) + '.lean'
    for p, d in srcroots.items():
        f = os.path.join(d, rel)
        if os.path.exists(f): return p, f
    return None, None
proj = set()
direct = set()
for top in ('OAI', 'ComparatorChallenges'):
    for dp, _, fs in os.walk(os.path.join(root, top)):
        for f in fs:
            if f.endswith('.lean'):
                proj.add(os.path.relpath(os.path.join(dp, f[:-5]), root).replace('/', '.'))
                for x in imp.findall(open(os.path.join(dp, f), 'rb').read()):
                    direct.add(x.decode())
direct = {d for d in direct if d not in proj and d != 'OAI'}
seen, todo = {}, list(direct)
while todo:
    m = todo.pop()
    if m in seen: continue
    p, f = find(m)
    if p is None: seen[m] = None; continue
    seen[m] = p
    todo += [x.decode() for x in imp.findall(open(f, 'rb').read()) if x.decode() not in seen]
reach = collections.Counter(p for p in seen.values() if p)
def total(p):
    n = 0
    for dp, dn, fs in os.walk(srcroots[p]):
        dn[:] = [d for d in dn if d not in ('.lake', '.git', 'lake-packages')]
        n += sum(f.endswith('.lean') for f in fs)
    return n
print(f"project modules {len(proj)}; distinct external modules directly imported {len(direct)}; reached transitively {sum(reach.values())}; unresolved {sum(1 for v in seen.values() if v is None)}")
for p, n in reach.most_common():
    t = total(p) if p != '<lean-core>' else None
    print(f"{p:32s} reached {n:6d}" + (f" / {t:6d} .lean files = {100*n/t:5.1f}%" if t else ''))
