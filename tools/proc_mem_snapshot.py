#!/usr/bin/env python3
"""proc_mem_snapshot: per-process memory of the running Lean compiles, split into private heap and shared mapped files.

Purpose: understand why a batch of Lean compiles needs far more memory than an earlier one. For each real `lean` process it shows the
module being compiled, how long it has run, RssAnon (private heap: must fit in RAM or swap) and RssFile (mapped .olean pages: shared and
evictable, but the hot part stalls everything when evicted), plus totals and what else is using memory. Read-only.
Usage: proc_mem_snapshot.py [--repeat N --every S]   (default one snapshot)
"""
import os, re, sys, time, argparse
ap = argparse.ArgumentParser(); ap.add_argument('--repeat', type=int, default=1); ap.add_argument('--every', type=float, default=10); a = ap.parse_args()
def st(pid):
    d = {}
    try:
        for l in open(f'/proc/{pid}/status'):
            if l.startswith(('VmRSS', 'RssAnon', 'RssFile', 'RssShmem')): k, v = l.split(':'); d[k] = int(v.split()[0]) / 2**20
    except OSError: return None
    return d
def snap():
    rows = []; other = {}
    for p in os.listdir('/proc'):
        if not p.isdigit(): continue
        try: exe = os.readlink(f'/proc/{p}/exe'); args = open(f'/proc/{p}/cmdline', 'rb').read().split(b'\0')
        except OSError: continue
        s = st(p)
        if not s: continue
        name = os.path.basename(exe)
        if name == 'lean' and '.elan/toolchains' in exe and len(args) > 1 and not any(x in (b'--server', b'--worker') for x in args[:3]) and b'.lean' in b' '.join(args):
            mod = next((x.decode() for x in args if x.endswith(b'.lean')), '?'); mod = re.sub(r'.*/src/lean/', '', mod)
            up = time.time() - os.stat(f'/proc/{p}').st_ctime
            rows.append((s['RssAnon'], s['RssFile'], up, mod))
        else: other[name] = other.get(name, 0) + s.get('RssAnon', 0)
    return rows, other
for i in range(a.repeat):
    rows, other = snap(); rows.sort(reverse=True)
    mi = {l.split(':')[0]: int(l.split()[1]) / 2**20 for l in open('/proc/meminfo')}
    print(f"{time.strftime('%H:%M:%S')}  {len(rows)} compiles: private {sum(r[0] for r in rows):.1f} GiB, mapped-file (shared) {sum(r[1] for r in rows):.1f} GiB;  MemAvailable {mi['MemAvailable']:.1f} GiB, swap used {mi['SwapTotal'] - mi['SwapFree']:.1f} GiB")
    print(f"  {'anon GiB':>8s} {'file GiB':>8s} {'age s':>6s}  module")
    for an, fi, up, mod in rows[:12]: print(f"  {an:8.2f} {fi:8.2f} {up:6.0f}  {mod[-95:]}")
    top = sorted(other.items(), key=lambda x: -x[1])[:5]; print('  other private memory by program:', ', '.join(f'{k} {v:.1f}' for k, v in top))
    if i + 1 < a.repeat: time.sleep(a.every)
