#!/usr/bin/env python3
"""nanoda_cost_proxy: can the cost of each declaration (hence the useful thread count) be guessed from the export alone, without running nanoda?

Purpose: nanoda's wall time at N threads follows from per-declaration check times (tools/nanoda_thread_model.py). Those need a run. This tests cheap
static proxies computed in one pass over the export: for each theorem/definition/opaque/axiom record, the number of expression lines and the bytes
emitted since the previous declaration record (lean4export writes an expression just before its first use, so this is roughly what that declaration
adds), and the number of lines mentioning of_decide_eq_true (kernel computation). It compares each proxy with the measured per-declaration time from a
timing file of the same export (rank correlation, and how many of the 10 costliest declarations the proxy also puts in its own top 10 / top 50) so we
learn whether the longest declaration (which sets the thread count) can be spotted statically.
Usage: nanoda_cost_proxy.py EXPORT TIMES_FILE
"""
import sys, json, re
exp, times = sys.argv[1], sys.argv[2]
names = {0: ''}; cur = []; recs = []; span_lines = span_bytes = 0; dec = 0
decide_id = None
for line in open(exp, 'rb'):
    if line.startswith(b'{"in"'):
        d = json.loads(line); nid = d['in']
        if 'str' in d:
            p = names.get(d['str']['pre'], ''); names[nid] = (p + '.' if p else '') + d['str']['str']
            if names[nid] == 'of_decide_eq_true': decide_id = nid
        else: names[nid] = names.get(d['num']['pre'], '') + '.' + str(d['num']['i'])
        continue
    if line.startswith((b'{"thm"', b'{"def"', b'{"opaque"', b'{"axiom"')):
        k = line[2:line.index(b'"', 3)].decode(); m = re.search(rb'"name":(\d+)', line)
        recs.append((names.get(int(m.group(1)), '?'), span_lines, span_bytes, dec)); span_lines = span_bytes = dec = 0; continue
    span_lines += 1; span_bytes += len(line)
    if decide_id is not None and (b'"name":%d,' % decide_id) in line: dec += 1
T = {}
for l in open(times):
    p = l.rstrip('\n').split('\t')
    if p[0] == 'E': T[p[4]] = int(p[3])
rows = [(T[n], n, sl, sb, dc) for n, sl, sb, dc in recs if n in T]
print(f"{len(recs)} declaration records in the export, {len(rows)} matched to a timing")


def ranks(v):
    o = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v)
    for k, i in enumerate(o): r[i] = k
    return r


def rho(a, b):
    ra, rb = ranks(a), ranks(b); n = len(a); ma = sum(ra) / n; mb = sum(rb) / n
    return sum((x - ma) * (y - mb) for x, y in zip(ra, rb)) / (sum((x - ma) ** 2 for x in ra) ** .5 * sum((y - mb) ** 2 for y in rb) ** .5)


t = [r[0] for r in rows]; top = lambda v, k: set(sorted(range(len(v)), key=lambda i: -v[i])[:k])
for label, j in (('expression lines', 2), ('bytes', 3), ('of_decide_eq_true lines', 4)):
    v = [r[j] for r in rows]
    print(f"{label:26s} rank correlation with measured time {rho(t, v):5.2f}; of the 10 slowest declarations, {len(top(t, 10) & top(v, 10))} in the proxy's top 10 and {len(top(t, 10) & top(v, 50))} in its top 50")
big = sorted(rows, reverse=True)[:5]
print('slowest declarations (us, lines, bytes, decide lines):'); [print('  ', r[0], r[2], r[3], r[4], r[1][:70]) for r in big]
