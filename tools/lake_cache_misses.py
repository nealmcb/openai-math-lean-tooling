#!/usr/bin/env python3
"""lake_cache_misses: which modules of a Lake build are missing from a cache mapping, and which of those are root misses.

Purpose: a fresh build of the Yang-Mills submission with our published cache (2026-11-12) compiled hundreds of modules instead of
none. Each module's .trace records its input hash ("depHash"), which is the key Lake looks up in the mapping, and the trace inputs
of its imports. A module missing from the mapping is either a root miss (all its in-project imports are in the mapping, so its own
key differs from the one recorded, or it was never converted) or a consequence (an import is missing, so its key changes too). Reads
every .trace under BUILD/lib/lean whose module is in the project (MODULE_PREFIXES), prints the counts and the root misses with their
in-project imports.
Usage: lake_cache_misses.py BUILD_DIR MAPPING.jsonl PREFIX [PREFIX ...]   (e.g. .lake/build map-all.jsonl YM Challenge Solution)
"""
import json, os, sys

build, mapping, prefixes = sys.argv[1], sys.argv[2], tuple(sys.argv[3:])
keys = {json.loads(l)[0] for l in open(mapping) if l.startswith('[')}
root = os.path.join(build, 'lib', 'lean')
dep, imports = {}, {}


def imports_of(inputs):   # module names in the "imports" part of a trace's deps
    out = []
    def walk(x):
        if isinstance(x, list):
            if len(x) == 2 and isinstance(x[0], str) and x[0] == 'imports': out.extend(i[0].split(' ')[0].split(':')[0] for i in x[1]); return
            for y in x: walk(y)
    walk(inputs)
    return out


for dp, _, fs in os.walk(root):
    for f in fs:
        if f.endswith('.trace'):
            m = os.path.relpath(os.path.join(dp, f[:-6]), root).replace(os.sep, '.')
            if not m.startswith(prefixes): continue
            t = json.load(open(os.path.join(dp, f)))
            dep[m] = t.get('depHash'); imports[m] = [i for i in imports_of(t.get('inputs', [])) if i.startswith(prefixes)]
missing = {m for m, h in dep.items() if h not in keys}
roots = sorted(m for m in missing if all(i not in missing for i in imports[m]))
print(f'{len(dep)} project modules with a trace; {len(dep) - len(missing)} in the mapping; {len(missing)} missing; {len(roots)} root misses')
for m in roots[:40]: print(f'  {m} {dep[m]}  imports: {", ".join(imports[m]) or "-"}')
