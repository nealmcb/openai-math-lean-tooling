#!/usr/bin/env python3
"""closure_sizes: per-module transitive in-repo import-closure size, from source text.

Purpose: predict the worst-case per-process VMA need (~5 x (closure incl. external
deps) + ~40 for Lean v4.34.1) for every module a Lake target compiles, to find the
modules most likely to hit vm.max_map_count without building everything.
Usage: closure_sizes.py LEAN_ROOT_DIR Root [Root...]  -> JSON lines to stdout (module, in_repo_closure)
Closure counts include the module itself and in-repo modules only; add the external
(Mathlib etc.) module count separately. Bitset-based, one pass in post-order.
"""
import sys, os, re, json
sys.setrecursionlimit(1000000)
root = sys.argv[1]
imp = re.compile(rb"^\s*(?:public\s+|meta\s+)*import\s+(?:public\s+|meta\s+)*(\S+)", re.M)
edges, idx = {}, {}
def path(m): return os.path.join(root, *m.split('.')) + '.lean'
order = []
stack = [(m, False) for m in sys.argv[2:]]
state = {}
while stack:
    m, done = stack.pop()
    if done: order.append(m); continue
    if m in state: continue
    if not os.path.exists(path(m)): state[m] = 2; continue
    state[m] = 1
    deps = [x.decode() for x in imp.findall(open(path(m), 'rb').read())]
    deps = [d for d in deps if os.path.exists(path(d))]
    edges[m] = deps
    stack.append((m, True))
    stack += [(d, False) for d in deps if d not in state]
bits = {}
for m in order:   # post-order: deps first
    idx[m] = len(idx)
for m in order:
    b = 1 << idx[m]
    for d in edges[m]:
        b |= bits[d]
    bits[m] = b
for m in order:
    print(json.dumps(dict(module=m, in_repo_closure=bin(bits[m]).count('1'), direct=len(edges[m]))))
