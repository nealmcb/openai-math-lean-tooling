#!/usr/bin/env python3
"""predict_vmas: predicted per-process VMA count for importing each project module, from source imports only.

Purpose: test "big families are more likely to hit vm.max_map_count" without building anything. For Lean v4.34.1
a process importing module X maps ~ 40 + 5*M + O files, where M = modules in X's import closure built with the module
system (they map .olean/.server/.private/.ir/.sig) and O = ordinary modules (only .olean). Validated against
measurements in ../REPORT.md (sections 2 and 3) (Mathlib alone: 53.8k; Progressions.Main: 58,571 observed).
Module-system detection: file's first non-comment line is `module`. Externals are resolved in .lake/packages and the
toolchain src dir. Usage: predict_vmas.py LEAN_ROOT TOOLCHAIN_SRC OUT.jsonl
Prints the top modules and the maximum over all non-aggregator modules.
"""
import sys, os, re, json
root, tc, out = sys.argv[1:4]
imp = re.compile(rb"^\s*(?:public\s+|meta\s+)*import\s+(?:public\s+|meta\s+)*(\S+)", re.M)
modsys = re.compile(rb"^(?:\s*(?:/-.*?-/|--[^\n]*)\s*)*module\b", re.S)
pk = os.path.join(root, '.lake/packages')
roots = {p: os.path.join(pk, p) for p in os.listdir(pk)}
roots['<core>'] = tc
def ext_path(m):
    rel = os.path.join(*m.split('.')) + '.lean'
    for d in roots.values():
        f = os.path.join(d, rel)
        if os.path.exists(f): return f
proj = {}
for top in ('OAI', 'ComparatorChallenges'):
    for dp, _, fs in os.walk(os.path.join(root, top)):
        for f in fs:
            if f.endswith('.lean'):
                proj[os.path.relpath(os.path.join(dp, f[:-5]), root).replace('/', '.')] = os.path.join(dp, f)
proj['OAI'] = os.path.join(root, 'OAI.lean')
sys.setrecursionlimit(1000000)
# external graph: BFS from all external imports of project modules, then bottom-up bitsets
ems, eimps = {}, {}
pdirect, pext_roots = {}, {}
for m, f in proj.items():
    ds = [d.decode() for d in imp.findall(open(f, 'rb').read())]
    pdirect[m] = [d for d in ds if d in proj]
    pext_roots[m] = [d for d in ds if d not in proj]
todo = [d for v in pext_roots.values() for d in v]
while todo:
    x = todo.pop()
    if x in eimps: continue
    f = ext_path(x)
    if f is None: eimps[x] = None; continue
    data = open(f, 'rb').read()
    ems[x] = bool(modsys.match(data))
    eimps[x] = [d.decode() for d in imp.findall(data)]
    todo += [d for d in eimps[x] if d not in eimps and d not in proj]
eidx = {x: i for i, x in enumerate(x for x in eimps if eimps[x] is not None)}
eb = {}
for r in list(eidx):
    if r in eb: continue
    st = [(r, 0)]
    while st:
        x, k = st.pop()
        if k == 0:
            if x in eb or x not in eidx: continue
            eb[x] = None
            st.append((x, 1)); st += [(d, 0) for d in eimps[x] if d in eidx and d not in eb]
        else:
            b = 1 << eidx[x]
            for d in eimps[x]:
                if d in eidx: b |= eb[d] or 0
            eb[x] = b
pext = {}
for m, ds in pext_roots.items():
    b = 0
    for d in ds:
        if d in eidx: b |= eb[d]
    pext[m] = b
msmask = 0
for x, i in eidx.items():
    if ems.get(x): msmask |= 1 << i
# in-repo closure bitsets
pidx = {m: i for i, m in enumerate(proj)}
pb, pe, order, state = {}, {}, [], {}
for r in proj:
    if r in state: continue
    st = [(r, 0)]
    while st:
        m, k = st.pop()
        if k == 0:
            if m in state: continue
            state[m] = 1
            st.append((m, 1)); st += [(d, 0) for d in pdirect[m] if d not in state]
        else: order.append(m)
for m in order:
    b = 1 << pidx[m]; e = pext[m]
    for d in pdirect[m]: b |= pb[d]; e |= pe[d]
    pb[m] = b; pe[m] = e
rows = []
for m in order:
    O = bin(pb[m]).count('1') - 0  # includes itself, ordinary in-repo modules
    Mx = bin(pe[m] & msmask).count('1'); Ox = bin(pe[m] & ~msmask).count('1')
    rows.append(dict(module=m, in_repo=O, ext_module_system=Mx, ext_ordinary=Ox, predicted_vmas=40 + 5 * Mx + O + Ox))
with open(out, 'w') as f:
    for r in rows: f.write(json.dumps(r) + '\n')
rows.sort(key=lambda r: -r['predicted_vmas'])
nonagg = [r for r in rows if r['module'] != 'OAI']
print('modules', len(rows), 'external modules', len(eidx), 'module-system', sum(1 for x in eidx if ems.get(x)))
for r in rows[:6]: print(r)
print('max excluding root OAI:', nonagg[0])
print('modules predicted > 65530 excluding root:', sum(r['predicted_vmas'] > 65530 for r in nonagg))
for r in rows:
    if r['module'] == 'OAI.Combinatorics.Progressions.Main': print('Progressions.Main:', r)
