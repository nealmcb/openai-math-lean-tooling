#!/usr/bin/env python3
"""importclosure: transitive in-repo import closure of root modules, from source text.

Purpose: size the set of OAI/ComparatorChallenges modules a Lake target compiles
("don't assume source-file count == modules compiled", see ../lean_verification_limits_prompt.md).
Usage: importclosure.py LEAN_ROOT_DIR Module [Module...]   -> prints counts, closure to stdout with --list
Only modules whose .lean exists under LEAN_ROOT_DIR are followed (external deps ignored).
"""
import sys, os, re
root = sys.argv[1]; todo = [m for m in sys.argv[2:] if m != '--list']
seen = set(); imp = re.compile(rb"^\s*(?:public\s+|meta\s+)*import\s+(?:public\s+|meta\s+)*(\S+)", re.M)
while todo:
    m = todo.pop()
    if m in seen: continue
    p = os.path.join(root, *m.split('.')) + '.lean'
    if not os.path.exists(p): continue
    seen.add(m)
    todo += [x.decode() for x in imp.findall(open(p, 'rb').read())]
print(len(seen), 'in-repo modules in closure')
if '--list' in sys.argv: print('\n'.join(sorted(seen)))
