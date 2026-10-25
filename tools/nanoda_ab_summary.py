#!/usr/bin/env python3
"""nanoda_ab_summary: summarize an output file of tools/nanoda_ab.py (two builds, the first is the baseline).

Purpose: nanoda_lib issue 62. After a sweep, say how many configurations have a complete record for both builds, which ones the second build newly
passes or newly fails, where it is slower or uses more memory, which machines produced the records, and how many records are missing.
Usage: nanoda_ab_summary.py RESULTS.jsonl [LIST_FILE ...]   (the optional list files, one NAME[:...] per line, define the expected configurations)
"""
import sys, json, collections
rs = [json.loads(l) for l in open(sys.argv[1])]
expected = [l.split(':')[0].strip() for f in sys.argv[2:] for l in open(f) if l.strip()]
done, reg = {}, [r for r in rs if r.get('regression')]
for r in rs:
    if r.get('label') and 'rc' in r: done.setdefault(r['config'], {})[r['label']] = r
labels = list(dict.fromkeys(r['label'] for r in rs if r.get('label')))
b, p = labels[0], labels[1]
both = {c: v for c, v in done.items() if len(v) >= 2}
print(f'{len(rs)} lines; {len(both)} configurations with both builds' + (f' of {len(expected)} expected' if expected else '') + f'; {len(reg)} regression lines; builds {b} (baseline) and {p}')
if expected: print('missing:', sorted(set(expected) - set(both)))
print(f'newly passing ({p} passes, {b} fails):', sorted(c for c, v in both.items() if v[b]['rc'] != 0 and v[p]['rc'] == 0))
print(f'newly failing ({p} fails, {b} passes):', sorted(c for c, v in both.items() if v[b]['rc'] == 0 and v[p]['rc'] != 0))
print('both fail:', sorted(c for c, v in both.items() if v[b]['rc'] != 0 and v[p]['rc'] != 0))
ok = {c: v for c, v in both.items() if v[b]['rc'] == 0 and v[p]['rc'] == 0}
print(f'both pass: {len(ok)}')
print(f'{p} more than 1.3x slower and over 60 s:', sorted((c, v[b]['wall_s'], v[p]['wall_s']) for c, v in ok.items() if v[p]['wall_s'] > 1.3 * v[b]['wall_s'] and v[p]['wall_s'] > 60))
print(f'{p} more than 1.3x memory and over 2 GiB:', sorted((c, v[b]['rss_gib'], v[p]['rss_gib']) for c, v in ok.items() if v[b]['rss_gib'] and v[p]['rss_gib'] and v[p]['rss_gib'] > 1.3 * v[b]['rss_gib'] and v[p]['rss_gib'] > 2))
tb, tp = sum(v[b]['wall_s'] for v in ok.values()), sum(v[p]['wall_s'] for v in ok.values())
print(f'total wall time over the {len(ok)} passing configurations: {b} {tb / 3600:.1f} h, {p} {tp / 3600:.1f} h (ratio {tp / tb:.3f})')
hosts = collections.Counter((r['host'].get('instance_type'), r['host'].get('lifecycle')) for r in rs if r.get('host') and r.get('label'))
print('records by machine type (only records written after host tracking was added carry one):', dict(hosts))
