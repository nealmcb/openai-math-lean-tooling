#!/usr/bin/env python3
"""source_audit: what do OAI modules contain that a successful build does not rule out?

Purpose: a module that builds has been elaborated and every declaration passed the Lean kernel, but a build does not reject `sorry`
(a warning), new `axiom`s, `native_decide` (compiled evaluation, trusted through an extra axiom) or `unsafe` code; Comparator rejects
those only for the theorems a configuration names and their dependencies. This counts those constructs, and the declarations a
module makes, in the source text of two groups: the modules reachable from OAI.lean that no Comparator configuration reaches
(results/comparator-solution-closure.txt), and the modules in the configurations' closures. Comments (`--` and `/- -/`) are removed
first; strings are not, so counts are approximate. Usage: source_audit.py   (reads about 1.2 GB of source, 15 to 30 s)
"""
import json, os, re
base = '/home/srv/s/math/openai-math'; src = base + '/src/lean'
closure = {l.strip() for l in open(base + '/results/comparator-solution-closure.txt') if l.strip()}
reach = [json.loads(l)['module'] for l in open(base + '/results/oai-closure-sizes.jsonl')]
groups = {'reachable from OAI.lean, in no config closure': [m for m in reach if m != 'OAI' and m not in closure], "in the configs' closures": sorted(closure)}
cm = re.compile(r'/-.*?-/|--[^\n]*', re.S)
pats = {'sorry': r'\bsorry\b', 'axiom': r'^\s*(?:private\s+|protected\s+)?axiom\b', 'native_decide': r'\bnative_decide\b|decide\s*\+native', 'unsafe': r'\bunsafe\b',
        'implemented_by/extern': r'@\[[^\]]*\b(?:implemented_by|extern)\b', 'theorem/lemma': r'^\s*(?:@\[[^\]]*\]\s*)?(?:private\s+|protected\s+)?(?:theorem|lemma)\b'}
cp = {k: re.compile(v, re.M) for k, v in pats.items()}
for name, mods in groups.items():
    tot = {k: 0 for k in pats}; withk = {k: 0 for k in pats}; n = 0; nbytes = 0
    for m in mods:
        p = os.path.join(src, *m.split('.')) + '.lean'
        try: t = open(p, encoding='utf-8', errors='replace').read()
        except OSError: continue
        n += 1; nbytes += len(t); t = cm.sub(' ', t)
        for k, c in cp.items():
            c_n = len(c.findall(t)); tot[k] += c_n; withk[k] += c_n > 0
    print(f"{name}: {n} modules, {nbytes / 1e6:.0f} MB")
    for k in pats: print(f"   {k:24s} {tot[k]:8d} occurrences in {withk[k]:6d} modules")
