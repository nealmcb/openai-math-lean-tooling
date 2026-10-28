#!/usr/bin/env python3
"""arena_times: per-test result, wall time and peak memory of Lean Kernel Arena checkers, from the published pages.

Purpose: compare checkers' speed on the Arena's inputs (Neal, 2026-10-27: how slow is lean4lean, the kernel written in Lean?), e.g.
on the whole-Mathlib export. Reads https://arena.lean-lang.org/checker/NAME/ for each NAME and prints one tab-separated line per
test: test, then result / wall time / max RSS for each checker. Only tests matching PATTERN (a regex, default: all).
Usage: arena_times.py CHECKER [CHECKER ...] [--tests PATTERN]     e.g. arena_times.py official nanoda lean4lean --tests 'mathlib|perf/'
"""
import re, sys, urllib.request

args = sys.argv[1:]
pat = re.compile(args[args.index('--tests') + 1]) if '--tests' in args else re.compile('')
checkers = [a for i, a in enumerate(args) if a != '--tests' and (i == 0 or args[i - 1] != '--tests')]


def results(name):
    page = urllib.request.urlopen(f'https://arena.lean-lang.org/checker/{name}/', timeout=60).read().decode()
    parts = re.split(r'id="test-', page)[1:]
    out = {}
    for p in parts:
        test = p.split('"', 1)[0]
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', p[:6000]))
        r = re.search(r'Test result: (\S+ \w+)', text)
        w = re.search(r'wall time: ([\d.]+ ?\w+)', text)
        m = re.search(r'max rss memory: ([\d.]+ ?\w+)', text)
        out[test] = '/'.join(x.group(1) if x else '-' for x in (r, w, m))
    return out


data = {c: results(c) for c in checkers}
print('test\t' + '\t'.join(checkers))
for t in sorted(set().union(*data.values())):
    if pat.search(t): print(t + '\t' + '\t'.join(data[c].get(t, '-') for c in checkers))
