#!/usr/bin/env python3
"""config_changes: field-by-field changes of the Comparator configurations between two openai/math commits.

Purpose: an update can change what a configuration checks without touching a proof (e.g. dropping names from `definition_names`, changing
`permitted_axioms`, moving the solution module), so after pulling openai/math, list for each new, removed or changed config which fields
changed and how (list fields as removed/added names), plus whether its challenge file changed. Written 2026-10-27 for fd4aeeb2ee -> 7ef5c0cc5.
Usage: config_changes.py OLD [NEW=HEAD]   (the checkout is src/ next to tools/, or $CHECKOUT/src)
"""
import json, os, subprocess, sys

here = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
src = os.path.join(os.environ.get('CHECKOUT', here), 'src')
old, new = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else 'HEAD'


def git(*a): return subprocess.run(['git', '-C', src, *a], check=True, capture_output=True, text=True).stdout


def configs(rev):
    return {p: json.loads(git('show', f'{rev}:{p}')) for p in git('ls-tree', '-r', '--name-only', rev, '--', 'lean/ComparatorChallenges').splitlines()
            if p.endswith('.json')}


a, b = configs(old), configs(new)
changed_files = set(git('diff', '--name-only', old, new, '--', 'lean').splitlines())
for p in sorted(a.keys() | b.keys()):
    name = p.removeprefix('lean/ComparatorChallenges/').removesuffix('.json')
    if p not in a: print(f'{name}: new'); continue
    if p not in b: print(f'{name}: removed'); continue
    x, y = a[p], b[p]
    challenge = 'lean/' + y['challenge_module'].replace('.', '/') + '.lean'
    notes = [f'challenge file changed ({challenge})'] if challenge in changed_files else []
    for k in sorted(x.keys() | y.keys()):
        u, v = x.get(k), y.get(k)
        if u == v: continue
        if isinstance(u, list) or isinstance(v, list):
            gone, came = [n for n in u or [] if n not in (v or [])], [n for n in v or [] if n not in (u or [])]
            notes.append(f'{k}: ' + ', '.join(filter(None, [f'-{len(gone)} ({", ".join(gone)})' if gone else '',
                                                           f'+{len(came)} ({", ".join(came)})' if came else ''])))
        else:
            notes.append(f'{k}: {u!r} -> {v!r}')
    if notes: print(f'{name}: ' + '; '.join(notes))
