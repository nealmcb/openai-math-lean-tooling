#!/usr/bin/env python3
"""overnight_status: summarize results/cmp-all/all.jsonl into STATUS.md (counts, failures, timing, disk, ETA). No model tokens.
Usage: overnight_status.py   (writes /home/srv/s/math/openai-math/results/cmp-all/STATUS.md; run hourly by tmux window)"""
import json, os, shutil, datetime, collections
base = '/home/srv/s/math/openai-math'; R = base + '/results/cmp-all'
last = {}
for l in open(R + '/all.jsonl'):
    d = json.loads(l); last[d['config']] = d          # last record per config wins
total = len(json.load(open(base + '/results/config-solution-size.json')))
c = collections.Counter(d['outcome'] for d in last.values())
acc = [d for d in last.values() if d['outcome'] == 'accepted' and d.get('build_s') is not None]
bad = [d for d in last.values() if d['outcome'] != 'accepted']
cs = [d['cmp_s'] for d in acc if d.get('cmp_s')]; bs = [d['build_s'] for d in acc]
free = shutil.disk_usage('/home').free / 2**30
drv = open(R + '/driver.log').read().strip().splitlines()[-1:] if os.path.exists(R + '/driver.log') else []
lines = [f"# Comparator overnight status ({datetime.datetime.now().astimezone().isoformat(timespec='seconds')})", '',
         f"configs recorded {len(last)}/{total}; outcomes {dict(c)}", f"free disk {free:.0f} GiB; ALERT file: {os.path.exists(R + '/ALERT')}; STOP file: {os.path.exists(R + '/STOP')}",
         f"accepted with timings {len(acc)}: median build {sorted(bs)[len(bs)//2] if bs else 0:.0f}s, median check {sorted(cs)[len(cs)//2] if cs else 0:.0f}s, total build {sum(bs)/3600:.1f}h, total check {sum(cs)/3600:.1f}h" if acc else "no timings yet",
         f"last driver line: {drv}", '', '## Not accepted (needs a human look)']
for d in bad: lines.append(f"- {d['config']}: {d['outcome']} {d.get('detail','')[:200]} (vmamon: {d.get('vmamon_class')})")
def built(m): return os.path.exists(base + '/src/lean/.lake/build/lib/lean/' + '/'.join(m.split('.')) + '.olean')
allc = open(base + '/results/comparator-solution-closure.txt').read().split()
b = sum(built(m) for m in allc)
lines.insert(4, f"modules built: {b}/{len(allc)} = {100*b/len(allc):.1f}% of the Comparator solution closure; configs accepted {c['accepted']}/{total} = {100*c['accepted']/total:.1f}%")
open(R + '/STATUS.md', 'w').write('\n'.join(lines) + '\n')
