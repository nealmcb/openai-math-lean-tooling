#!/usr/bin/env python3
"""cgroup_census: which processes share a cgroup, and which cgroup would systemd-oomd kill first?

Purpose: systemd-oomd (Ubuntu 22.04, systemd 249) kills a whole LEAF cgroup (every process in it) when the user session's memory
pressure stays above the limit; candidates are ranked "from the ones with the most reclaim activity to the least" (oomd.conf(5)).
So what dies together is decided by cgroup membership, not by what the user considers one application. This lists every cgroup under
the user manager with its processes, memory, swap, pressure and reclaim rate (pgscan pages/s over a short window), flags leaf
cgroups and memory.oom.group, and ranks them the way oomd does, so the likely victim and its collateral are visible before a crash.
Usage: cgroup_census.py [--window 3] [--min-mib 50] [--json]   (read-only)
"""
import os, sys, time, json, argparse, collections
ap = argparse.ArgumentParser(); ap.add_argument('--window', type=float, default=3, help='seconds between the two pgscan samples')
ap.add_argument('--min-mib', type=float, default=50, help='hide cgroups using less than this much memory and 0 reclaim')
ap.add_argument('--json', action='store_true'); a = ap.parse_args()
uid = os.getuid(); ROOT = f'/sys/fs/cgroup/user.slice/user-{uid}.slice/user@{uid}.service'


def rd(path, default=None):
    try: return open(path).read()
    except OSError: return default


def stat_kv(path):
    d = {}
    for l in (rd(path, '') or '').splitlines():
        p = l.split()
        if len(p) == 2 and p[1].lstrip('-').isdigit(): d[p[0]] = int(p[1])
    return d


def psi(path):
    out = {}
    for l in (rd(path, '') or '').splitlines():
        k = l.split()[0]; out[k] = float(l.split('avg10=')[1].split()[0])
    return out


def walk(root):
    out = []
    for dp, dn, fn in os.walk(root):
        if 'cgroup.procs' in fn: out.append(dp)
    return sorted(out)


def comms(path):
    c = collections.Counter()
    for pid in (rd(path + '/cgroup.procs', '') or '').split():
        n = (rd(f'/proc/{pid}/comm', '') or '?').strip(); c[n] += 1
    return c


groups = walk(ROOT); s1 = {g: stat_kv(g + '/memory.stat') for g in groups}; t1 = time.time()
time.sleep(a.window); dt = time.time() - t1; rows = []
for g in groups:
    s2 = stat_kv(g + '/memory.stat'); sc = (s2.get('pgscan', 0) - s1[g].get('pgscan', 0)) / dt
    cur = int(rd(g + '/memory.current', '0') or 0); sw = int(rd(g + '/memory.swap.current', '0') or 0)
    c = comms(g); n = sum(c.values()); sub = [d for d in os.listdir(g) if os.path.isdir(os.path.join(g, d)) and os.path.exists(os.path.join(g, d, 'cgroup.procs'))]
    if n == 0 and cur < a.min_mib * 2**20 and sc == 0: continue
    if cur < a.min_mib * 2**20 and sc == 0: continue
    p = psi(g + '/memory.pressure')
    rows.append(dict(cgroup=g[len(ROOT):] or '/', procs=n, mem_mib=round(cur / 2**20), swap_mib=round(sw / 2**20), psi_some10=p.get('some', 0), psi_full10=p.get('full', 0),
                     pgscan_per_s=round(sc), leaf=not sub, oom_group=(rd(g + '/memory.oom.group', '0') or '0').strip() == '1', top=dict(c.most_common(5))))
rows.sort(key=lambda r: (-r['pgscan_per_s'], -r['mem_mib']))
user = psi(ROOT + '/memory.pressure'); sysp = psi('/proc/pressure/memory')
if a.json: print(json.dumps(dict(user_manager_psi=user, system_psi=sysp, cgroups=rows), indent=1)); sys.exit()
print(f"user@{uid}.service memory pressure some/full avg10 = {user.get('some', 0):.1f}% / {user.get('full', 0):.1f}%   (oomd acts above 50% for 20 s)   system: {sysp.get('some', 0):.1f}%")
print(f"{'rank':>4s} {'procs':>5s} {'mem MiB':>8s} {'swap MiB':>8s} {'psi some':>8s} {'pgscan/s':>8s} leaf oomgrp  cgroup  [top processes]")
for i, r in enumerate(rows, 1):
    print(f"{i:4d} {r['procs']:5d} {r['mem_mib']:8d} {r['swap_mib']:8d} {r['psi_some10']:8.1f} {r['pgscan_per_s']:8d} {'Y' if r['leaf'] else '-':>4s} {'Y' if r['oom_group'] else '-':>6s}  {r['cgroup'][-62:]}  {r['top']}")
print("\noomd order = highest pgscan/s first, among leaf cgroups (and memory.oom.group=1). Everything in the chosen cgroup dies together.")
