#!/usr/bin/env python3
"""solution_coverage: how much of the OAI library do the Comparator solutions reach through their imports?

Purpose: nanoda checks (and Comparator exports) only the declarations reachable from the 416 solution theorems, i.e. the declarations of the modules in the union of
the solutions' import closures. This computes that union from source text (the same import scan as tools/importclosure.py), compares it with every OAI module
in the repository, and writes results/solution-coverage.json (counts, per top-level area) and results/uncovered-modules.txt (the modules no solution imports, one per line).
A module is "covered" when some solution imports it directly or transitively; a covered module can still contain declarations the solution does not use, so this is an
upper bound on declaration coverage. Needs only git and the source tree, runs in seconds.
Usage: solution_coverage.py
"""
import os, re, json, subprocess, collections
base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')); root = base + '/src/lean'
imp = re.compile(rb"^\s*(?:public\s+|meta\s+)*import\s+(?:public\s+|meta\s+)*(\S+)", re.M)
files = subprocess.run(['git', 'ls-files', 'OAI', 'OAI.lean'], cwd=root, capture_output=True, text=True).stdout.split()
allmods = {f[:-5].replace('/', '.') for f in files if f.endswith('.lean')}
sols = {json.load(open(f'{root}/ComparatorChallenges/{f}'))['solution_module'] for f in os.listdir(root + '/ComparatorChallenges') if f.endswith('.json')}
seen = set(); todo = list(sols)
while todo:
    m = todo.pop()
    if m in seen or m not in allmods: continue
    seen.add(m); todo += [x.decode() for x in imp.findall(open(os.path.join(root, *m.split('.')) + '.lean', 'rb').read())]
unc = sorted(allmods - seen)
area = lambda m: '.'.join(m.split('.')[:2])
by = collections.Counter(area(m) for m in unc); tot = collections.Counter(area(m) for m in allmods)
json.dump(dict(modules=len(allmods), solutions=len(sols), covered=len(seen), uncovered=len(unc), uncovered_by_area={a: [n, tot[a]] for a, n in by.most_common()}), open(base + '/results/solution-coverage.json', 'w'), indent=1)
open(base + '/results/uncovered-modules.txt', 'w').write('\n'.join(unc) + '\n')
print(f"{len(allmods)} OAI modules; {len(sols)} solutions reach {len(seen)} ({100 * len(seen) / len(allmods):.1f}%); {len(unc)} not reached")
for a, n in by.most_common(12): print(f"  {a}: {n} of {tot[a]} not reached")
