#!/usr/bin/env python3
"""recover_records: write all.jsonl records for Comparator checks whose recorder process died before finishing.

Purpose: tools/run_comparator_batch.py writes a config's record only after its check ends. If it is killed (for example an
accidental Ctrl-C) while the sandboxed check keeps running, the result is in the monitor directory
results/cmp-all/logs/<config>.mon (summary.json and stdout.log) but not in all.jsonl. This adds the missing records, marked
"recovered": true. It skips configs already accepted and any check still running. Build fields are unknown for these records.
Usage: recover_records.py [--dry-run]
"""
import json, os, re, sys, glob, subprocess, datetime as dt
base = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')); R = base + '/results/cmp-all'; root = base + '/src/lean'
dry = '--dry-run' in sys.argv
have = {json.loads(l)['config'] for l in open(R + '/all.jsonl') if json.loads(l).get('outcome') == 'accepted'}
n = 0
for mon in sorted(glob.glob(R + '/logs/*.mon')):
    name = os.path.basename(mon)[:-4]
    if name in have or not os.path.exists(mon + '/summary.json'): continue
    if subprocess.run(['pgrep', '-f', f'bin/comparator ComparatorChallenges/{name}.json'], capture_output=True).returncode == 0: continue
    cfg = json.load(open(f'{root}/ComparatorChallenges/{name}.json')); s = json.load(open(mon + '/summary.json'))
    text = open(mon + '/stdout.log', errors='replace').read()
    ok = 'Your solution is okay!' in text; m = re.findall(r'uncaught exception: (.*)', text)
    top = (s.get('top_processes') or [{}])
    rec = dict(config=name, solution=cfg['solution_module'], challenge=cfg['challenge_module'], nanoda=bool(cfg.get('enable_nanoda')),
               started=s.get('started'), build_skipped=True, recovered=True, cmp_s=s.get('wall_s'), peak_vmas=s.get('peak_per_process_vmas_sampled'),
               peak_rss_gib=round(max([t['max_rss'] for t in top] or [0]) / 2**30, 1), vmamon_class=s.get('classification'),
               outcome='accepted' if ok else 'rejected_or_error', detail=(m[-1][:300] if m and not ok else ''))
    print(('would add ' if dry else 'adding ') + json.dumps({k: rec[k] for k in ('config', 'outcome', 'cmp_s', 'peak_vmas', 'peak_rss_gib')}))
    if not dry: open(R + '/all.jsonl', 'a').write(json.dumps(rec) + '\n')
    n += 1
print(f'{n} record(s) {"would be " if dry else ""}recovered')
