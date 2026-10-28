#!/usr/bin/env python3
"""find_bridge: can a Comparator solution's environment even mention the challenge's own definitions?

Purpose: Comparator rejected HodgeConjectureCMAbelianVarieties/main on 2026-10-28 ("Challenge and solution theorem statement do not
match") because the solution states the theorem with OAI's copies of the definitions, not the challenge's. A bridge (a lemma
identifying the two) can only exist in a module that imports the challenge's side. From source text, this computes the in-repo import
closures of the challenge and solution modules and reports: modules the two closures share; solution-closure modules that import a
challenge-only module; files in the solution closure, and then anywhere under the scanned trees, that mention any of the given NAMES
(e.g. a namespace such as HodgeCM, or a module prefix). Written 2026-10-28.
Usage: find_bridge.py CONFIG.json [--root MODPREFIX=DIR ...] [--name NAME ...] [--scan DIR ...]
  CONFIG relative to src/lean; --root as in tools/update_impact.py; --scan directories (relative to src/lean) searched in full for NAMES
  (default OAI). The checkout is src/ next to tools/, or $CHECKOUT/src.
"""
import json, os, re, sys

here = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
lean = os.path.join(os.environ.get('CHECKOUT', here), 'src', 'lean')
imp = re.compile(rb"^\s*(?:public\s+|meta\s+)*import\s+(?:public\s+|meta\s+)*(\S+)", re.M)
args = sys.argv[1:]
opts = {'--root': [], '--name': [], '--scan': []}
cfgpath, i = None, 0
while i < len(args):
    if args[i] in opts: opts[args[i]].append(args[i + 1]); i += 2
    else: cfgpath = args[i]; i += 1
roots = dict(r.split('=', 1) for r in opts['--root'])
names = opts['--name']; scan = opts['--scan'] or ['OAI']


def relpath(m):
    for prefix, d in roots.items():
        if m == prefix or m.startswith(prefix + '.'): return os.path.join(d, *m.split('.')) + '.lean'
    return os.path.join(*m.split('.')) + '.lean'


imports = {}
def deps(m):
    if m not in imports:
        p = os.path.join(lean, relpath(m))
        imports[m] = [x.decode() for x in imp.findall(open(p, 'rb').read())] if os.path.exists(p) else None
    return imports[m]


def closure(m):
    seen, todo = set(), [m]
    while todo:
        x = todo.pop()
        if x in seen or deps(x) is None: continue
        seen.add(x); todo += deps(x)
    return seen


cfg = json.load(open(os.path.join(lean, cfgpath)))
ch, so = closure(cfg['challenge_module']), closure(cfg['solution_module'])
shared, ch_only = ch & so, ch - so
print(f'challenge closure {len(ch)} in-repo modules, solution closure {len(so)}, shared {len(shared)}')
for m in sorted(shared): print('  shared:', m)
importers = sorted(m for m in so if any(d in ch_only for d in deps(m)))
print(f'solution-closure modules importing a challenge-only module: {len(importers)}')
for m in importers: print('  ', m, '->', [d for d in deps(m) if d in ch_only])
if names:
    pat = re.compile('|'.join(re.escape(n) for n in names).encode())
    hits = sorted(m for m in so if pat.search(open(os.path.join(lean, relpath(m)), 'rb').read()))
    print(f'solution-closure files mentioning {names}: {len(hits)}')
    for m in hits[:50]: print('  ', relpath(m))
    for d in scan:
        n_files, found = 0, []
        for dp, _, fs in os.walk(os.path.join(lean, d)):
            for f in fs:
                if f.endswith('.lean'):
                    n_files += 1; p = os.path.join(dp, f)
                    if pat.search(open(p, 'rb').read()): found.append(os.path.relpath(p, lean))
        print(f'files under {d}/ ({n_files} scanned) mentioning {names}: {len(found)}')
        for p in found[:50]: print('  ', p)
