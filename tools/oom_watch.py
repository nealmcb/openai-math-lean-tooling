#!/usr/bin/env python3
"""oom_watch: 1 Hz recorder of everything relevant to a memory-pressure kill, for post-mortems and for the memory lab.

Purpose: at 18:00 on 2026-10-11 systemd-oomd killed one cgroup holding the user's browser, terminal, Claude session and a build, and
nothing recorded the minutes before. This samples once a second (default) and appends JSON lines: system and user-session memory
pressure (some/full avg10), MemAvailable, swap used, and for the cgroups under the user manager the top N by memory (processes,
memory, swap, pressure, reclaim pgscan pages/s, leaf, oom.group, top process names). It notes each cgroup that disappears (killed) with
its last sample, and tails the journal for systemd-oomd lines. Cheap enough to leave running (about 1-2 ms per cgroup).
Usage: oom_watch.py [--out results/oom-lab/watch.jsonl] [--interval 1] [--top 8]     (Ctrl-C to stop)
"""
import os, sys, time, json, argparse, subprocess, collections, signal
ap = argparse.ArgumentParser(); ap.add_argument('--out', default='/home/srv/s/math/openai-math/results/oom-lab/watch.jsonl')
ap.add_argument('--interval', type=float, default=1.0); ap.add_argument('--top', type=int, default=8); a = ap.parse_args()
uid = os.getuid(); ROOT = f'/sys/fs/cgroup/user.slice/user-{uid}.slice/user@{uid}.service'
os.makedirs(os.path.dirname(a.out), exist_ok=True); out = open(a.out, 'a')
rd = lambda p, d='': (lambda f: f.read() if f else d)(open(p) if os.path.exists(p) else None)
def kv(p):
    d = {}
    for l in rd(p).splitlines():
        t = l.split()
        if len(t) == 2 and t[1].lstrip('-').isdigit(): d[t[0]] = int(t[1])
    return d
def psi(p):
    o = {}
    for l in rd(p).splitlines():
        if 'avg10=' in l: o[l.split()[0]] = float(l.split('avg10=')[1].split()[0])
    return o
def meminfo():
    m = {}
    for l in rd('/proc/meminfo').splitlines():
        k, v = l.split(':'); m[k] = int(v.split()[0])
    return m
def cgroups(): return [dp for dp, dn, fn in os.walk(ROOT) if 'cgroup.procs' in fn]
journal = subprocess.Popen(['journalctl', '--no-pager', '-f', '-n0', '-u', 'systemd-oomd', '-o', 'short-iso'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
os.set_blocking(journal.stdout.fileno(), False)
prev, last_seen, stop = {}, {}, [False]
signal.signal(signal.SIGINT, lambda *x: stop.__setitem__(0, True)); signal.signal(signal.SIGTERM, lambda *x: stop.__setitem__(0, True))
while not stop[0]:
    t = time.time(); mi = meminfo(); rows = {}
    for g in cgroups():
        st = kv(g + '/memory.stat'); cur = int(rd(g + '/memory.current', '0') or 0)
        pg = st.get('pgscan', 0); rate = (pg - prev.get(g, pg)) / a.interval if g in prev else 0; prev[g] = pg
        procs = rd(g + '/cgroup.procs').split()
        rows[g] = dict(cg=g[len(ROOT):] or '/', procs=len(procs), mem_mib=cur >> 20, swap_mib=int(rd(g + '/memory.swap.current', '0') or 0) >> 20,
                       psi_some=psi(g + '/memory.pressure').get('some', 0), pgscan_s=round(rate), leaf=not any(os.path.isdir(os.path.join(g, d)) and os.path.exists(os.path.join(g, d, 'cgroup.procs')) for d in os.listdir(g)),
                       oom_group=rd(g + '/memory.oom.group', '0').strip() == '1')
    gone = [last_seen[g] for g in last_seen if g not in rows]       # cgroups that vanished since last sample
    for g in rows:
        if rows[g]['procs']:
            c = collections.Counter((rd(f'/proc/{p}/comm', '?').strip()) for p in rd(g + '/cgroup.procs').split()); rows[g]['top'] = dict(c.most_common(4))
    last_seen = rows
    top = sorted(rows.values(), key=lambda r: (-r['pgscan_s'], -r['mem_mib']))[:a.top]
    jl = []
    try: jl = [l.strip() for l in journal.stdout.readlines()] if journal.stdout else []
    except Exception: pass
    out.write(json.dumps(dict(t=round(t, 2), iso=time.strftime('%H:%M:%S', time.localtime(t)), sys_psi=psi('/proc/pressure/memory'), user_psi=psi(ROOT + '/memory.pressure'),
                              avail_mib=mi['MemAvailable'] >> 10, swap_used_mib=(mi['SwapTotal'] - mi['SwapFree']) >> 10, top=top, vanished=gone, oomd=jl)) + '\n'); out.flush()
    time.sleep(max(0, a.interval - (time.time() - t)))
journal.terminate()
