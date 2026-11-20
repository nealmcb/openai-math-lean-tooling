#!/usr/bin/env python3
"""compare_lake_traces: show where two Lake traces of the same module differ.

Purpose: diagnose why a module's input hash ("depHash") differs between the build a cache was made from and a fresh build restored
from that cache (2026-11-13, the Yang-Mills cache: 9 root misses, tools/lake_cache_misses.py). A trace's "inputs" is a tree of
[label, hash] entries (the source, Lean version, options, and each import's hashes); this walks both trees in parallel and prints the
entries whose hashes differ, plus each trace's outputs (artifact hashes). Labels that embed absolute paths are compared with the
directory part removed, since the builds lived in different directories.
Usage: compare_lake_traces.py A.trace B.trace
"""
import json, re, sys

a, b = (json.load(open(p)) for p in sys.argv[1:3])
norm = lambda s: re.sub(r'/\S*/(?=[^/\s]+\.lean)', '.../', s) if isinstance(s, str) else s


def entries(x, path=()):   # yield (path, label, hash) for every [label, hash] leaf, in order
    if isinstance(x, list):
        if len(x) == 2 and isinstance(x[0], str) and isinstance(x[1], str): yield path, norm(x[0]), x[1]; return
        if len(x) == 2 and isinstance(x[0], str) and isinstance(x[1], list):
            for e in entries(x[1], path + (norm(x[0]),)): yield e
            return
        for y in x:
            for e in entries(y, path): yield e


print('depHash', a.get('depHash'), b.get('depHash'), 'same' if a.get('depHash') == b.get('depHash') else 'DIFFERENT')
ea = {(p, l): h for p, l, h in entries(a.get('inputs', []))}
eb = {(p, l): h for p, l, h in entries(b.get('inputs', []))}
for k in sorted(ea.keys() | eb.keys()):
    if ea.get(k) != eb.get(k): print('  differs:', ' > '.join(k[0] + (k[1],)), ea.get(k), eb.get(k))
print('outputs A:', json.dumps(a.get('outputs'))[:400])
print('outputs B:', json.dumps(b.get('outputs'))[:400])
