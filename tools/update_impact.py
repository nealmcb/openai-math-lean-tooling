#!/usr/bin/env python3
"""update_impact: what an openai/math update means for each Comparator configuration.

Purpose: after pulling a new openai/math commit, find the configurations that are new or whose
config, challenge or solution changed, and for each one count the in-repo modules in its import
closure and how many of them must be compiled because the published Lake cache (built at BASE)
cannot have them: a module is stale if its source is new or changed since BASE, or if anything it
imports (transitively) is stale, since Lake's hash covers the imports' hashes.
Written 2026-10-27 for the update fd4aeeb2ee -> 7ef5c0cc5.

Usage: update_impact.py BASE [CONFIG.json ...] [--root MODPREFIX=DIR ...] [--all] [--remaining]
  BASE      the openai/math commit the cache was built from (e.g. fd4aeeb2ee)
  CONFIG    paths relative to src/lean; default: every config that is new, changed, or whose
            closure contains a stale module (--all also prints the unaffected ones)
  --root    an extra source root, e.g. HodgeConjecture=ComparatorChallenges/HodgeConjectureCMAbelianVarieties
            (lean_lib srcDir entries in the lakefile); other modules resolve under src/lean itself
  --remaining  also count the stale modules of the whole library (every .lean under OAI/, ComparatorChallenges/ and the
            --root directories, plus the root module OAI) that none of the affected configurations' closures covers: what is
            left to build on a machine that has the BASE build and those closures (e.g. before refreshing the Lake cache);
            prints the count by top-level area
Prints one tab-separated line per configuration: name, status, closure size, stale modules.
The checkout is the src/ next to tools/, or $CHECKOUT/src if CHECKOUT is set.
Source text only: the import regex matches tools/importclosure.py, so it can miss imports made by
unusual syntax, and it ignores dependencies outside the repository (check that lake-manifest.json
did not change).
"""
import json, os, re, subprocess, sys

here = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
src = os.path.join(os.environ.get('CHECKOUT', here), 'src')
lean = os.path.join(src, 'lean')
imp = re.compile(rb"^\s*(?:public\s+|meta\s+)*import\s+(?:public\s+|meta\s+)*(\S+)", re.M)

args = sys.argv[1:]
roots = {}
while '--root' in args:
    i = args.index('--root'); prefix, d = args[i + 1].split('=', 1); roots[prefix] = d; del args[i:i + 2]
show_all = '--all' in args
remaining = '--remaining' in args
args = [a for a in args if a not in ('--all', '--remaining')]
base, configs = args[0], args[1:]


def git(*a): return subprocess.run(['git', '-C', src, *a], check=True, capture_output=True, text=True).stdout


def relpath(m):   # path of module m relative to src/lean
    for prefix, d in roots.items():
        if m == prefix or m.startswith(prefix + '.'): return os.path.join(d, *m.split('.')) + '.lean'
    return os.path.join(*m.split('.')) + '.lean'


changed = {l[len('lean/'):] for l in git('diff', '--name-only', base, 'HEAD', '--', 'lean').splitlines()}
old_configs = {l[len('lean/'):] for l in git('ls-tree', '-r', '--name-only', base, '--', 'lean/ComparatorChallenges').splitlines()}
imports, stale = {}, {}


def deps(m):   # in-repo imports of m, or None if m is not an in-repo module
    if m not in imports:
        p = os.path.join(lean, relpath(m))
        imports[m] = [x.decode() for x in imp.findall(open(p, 'rb').read())] if os.path.exists(p) else None
    return imports[m]


def is_stale(m):   # iterative post-order, so deep import chains don't hit the recursion limit
    todo = [(m, False)]
    while todo:
        x, done = todo.pop()
        if x in stale: continue
        ds = [d for d in deps(x) if deps(d) is not None]
        if done: stale[x] = relpath(x) in changed or any(stale[d] for d in ds); continue
        todo.append((x, True)); todo += [(d, False) for d in ds if d not in stale]
    return stale[m]


def closure(m):
    seen, todo = set(), [m]
    while todo:
        x = todo.pop()
        if x in seen or deps(x) is None: continue
        seen.add(x); todo += deps(x)
    return seen


if not configs:
    configs = sorted(os.path.relpath(os.path.join(dp, f), lean) for dp, _, fs in os.walk(os.path.join(lean, 'ComparatorChallenges'))
                     for f in fs if f.endswith('.json'))
covered = set()
for c in configs:
    cfg = json.load(open(os.path.join(lean, c)))
    mods = closure(cfg['challenge_module']) | closure(cfg['solution_module'])
    if any(is_stale(m) for m in mods) or c not in old_configs: covered |= mods
    n_stale = sum(is_stale(m) for m in mods)
    files = {c, relpath(cfg['challenge_module']), relpath(cfg['solution_module'])}
    status = 'new' if c not in old_configs else 'changed' if files & changed else 'deps-changed' if n_stale else 'same'
    if show_all or status != 'same':
        print(f"{os.path.splitext(c)[0].removeprefix('ComparatorChallenges/')}\t{status}\t{len(mods)}\t{n_stale}", flush=True)

if remaining:
    import collections
    every = {'OAI'}
    # module names are paths relative to src/lean, or to a --root directory for the modules under it
    for top, base_dir in [('OAI', ''), ('ComparatorChallenges', '')] + [(d, d) for d in roots.values()]:
        for dp, _, fs in os.walk(os.path.join(lean, top)):
            for f in fs:
                # a --root directory inside ComparatorChallenges/ is its own library (the lakefile excludes it there)
                if f.endswith('.lean') and not (base_dir == '' and any(os.path.join(dp, f).startswith(os.path.join(lean, d) + os.sep) for d in roots.values())):
                    every.add(os.path.relpath(os.path.join(dp, f), os.path.join(lean, base_dir))[:-5].replace(os.sep, '.'))
    stale_all = {m for m in every if deps(m) is not None and is_stale(m)}
    left = stale_all - covered
    print(f'stale modules in the whole library: {len(stale_all)}; covered by the affected configurations: {len(stale_all & covered)}; '
          f'left to build: {len(left)}')
    for area, n in collections.Counter('.'.join(m.split('.')[:2]) for m in left).most_common(25): print(f'  {n:6d}  {area}')
