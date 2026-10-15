#!/usr/bin/env python3
"""cloud_schedule_model: how long would building every module and running every check take on P cores? A list-scheduling simulation.

Purpose: size and price a cloud run before spending anything. Nodes are the 107,978 modules of the Comparator configurations' import
closures (results/comparator-solution-closure.txt), each with a compile time, and the 416 checks, each a single-core job (the official
kernel is single-threaded) that can start when its solution and challenge modules are built. P cores run the ready job with the
longest remaining path first (checks outrank compiles, so a long check starts as soon as it can). Times come from the laptop run:
compile time = the first recorded build time of the module (results/module-times.csv.gz; seconds measured under load, so an upper
bound), or for the modules without one the area's seconds per KB of source times the file size; check time = active check time
(results/cmp-all/configs.csv). --speed S divides the compile times by S and --check-speed C the check times by C (default: S), because
the pilot on an m7a.2xlarge (results/cloud-pilot) found them to differ: compiles about 4 times faster, single-threaded checks only 1.0 to 1.4 times. Not modelled: memory limits (heavy compiles
reach 7 to 10 GiB, checks 6.5 GiB typically and 26 GiB at most, so check that P cores come with about 2 GiB each or more), disk and
network, and the start-up work (toolchain install, Mathlib cache download). It reports the total work, the critical path, the
makespan, and when the last compile and the last check finish, for each P. Usage: cloud_schedule_model.py [--cores 16,96,192]
[--speed 1,1.5,2] [--check-speed 1.2]
"""
import os, re, csv, gzip, json, heapq, sys, collections
base = '/home/srv/s/math/openai-math'; src = base + '/src/lean'
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
cores = [int(x) for x in arg('--cores', '16,96,192').split(',')]; check_speed = arg('--check-speed', None); speeds = [float(x) for x in arg('--speed', '1,1.5,2').split(',')]
nodes = [l.strip() for l in open(base + '/results/comparator-solution-closure.txt') if l.strip()]; idx = {m: i for i, m in enumerate(nodes)}
imp = re.compile(rb"^\s*(?:public\s+|meta\s+)*import\s+(?:public\s+|meta\s+)*(\S+)", re.M)
size = [0] * len(nodes); deps = [[] for _ in nodes]
for i, m in enumerate(nodes):
    p = os.path.join(src, *m.split('.')) + '.lean'
    try: t = open(p, 'rb').read()
    except OSError: continue
    size[i] = len(t); deps[i] = sorted({idx[x.decode()] for x in imp.findall(t) if x.decode() in idx})
known = {r['module']: float(r['first_build_s']) for r in csv.DictReader(gzip.open(base + '/results/module-times.csv.gz', 'rt')) if r['likely_pause_artifact'] != '1'}
area = collections.defaultdict(lambda: [0.0, 0])
for i, m in enumerate(nodes):
    if m in known: a = m.split('.')[1] if '.' in m else m; area[a][0] += known[m]; area[a][1] += size[i]
glob = sum(v[0] for v in area.values()) / sum(v[1] for v in area.values())
dur = [known.get(m) if m in known else (area[m.split('.')[1]][0] / area[m.split('.')[1]][1] if '.' in m and area[m.split('.')[1]][1] else glob) * size[i] for i, m in enumerate(nodes)]
checks = []
for f in sorted(os.listdir(src + '/ComparatorChallenges')):
    if f.endswith('.json'):
        c = json.load(open(f'{src}/ComparatorChallenges/{f}'))
        checks.append((f[:-5], idx[c['solution_module']], idx.get(c['challenge_module'])))
act = {r['config']: float(r['check_active_s']) for r in csv.DictReader(open(base + '/results/cmp-all/configs.csv')) if r['check_active_s']}
N = len(nodes); total = N + len(checks)
users = [[] for _ in range(total)]; need = [0] * total; d = dur + [act[n] for n, _, _ in checks]
for i in range(N):
    need[i] = len(deps[i])
    for j in deps[i]: users[j].append(i)
for k, (n, s, c) in enumerate(checks):
    v = N + k; ds = [x for x in (s, c) if x is not None]; need[v] = len(set(ds))
    for j in set(ds): users[j].append(v)
order = []; indeg = need[:]; stack = [i for i in range(total) if indeg[i] == 0]
while stack:
    v = stack.pop(); order.append(v)
    for u in users[v]:
        indeg[u] -= 1
        if indeg[u] == 0: stack.append(u)
assert len(order) == total, 'cycle in the import graph?'
bl = d[:]                                              # bottom level: own time plus the longest path after it
for v in reversed(order):
    for u in users[v]: bl[v] = max(bl[v], d[v] + bl[u])
blc = d[:N]                                            # the same for compiles alone (no checks)
for v in reversed(order):
    if v < N:
        for u in users[v]:
            if u < N: blc[v] = max(blc[v], d[v] + blc[u])
cp = max(bl[i] for i in range(N)); work = sum(d[:N]); cwork = sum(d[N:])
print(f"{N} modules ({work / 3600:.0f} module-hours at laptop speed), {len(checks)} checks ({cwork / 3600:.0f} check-hours); longest chain of compiles {max(blc) / 3600:.1f} h (longest module-to-check path: {cp / 3600:.1f} h)")
print(f"longest single check {max(d[N:]) / 3600:.1f} h; checks over 1 h: {sum(1 for x in d[N:] if x > 3600)} ({sum(x for x in d[N:] if x > 3600) / 3600:.0f} h)")
print(f"{'cores':>5s} {'speed':>5s} {'makespan h':>10s} {'last compile h':>14s} {'last check h':>12s} {'core-hours used':>15s} {'utilisation':>11s}")
for P in cores:
    for sp in speeds:
        t = 0.0; free = P; ready = []; run = []; fin = [0.0] * total
        for v in range(total):
            if need[v] == 0: heapq.heappush(ready, (-(bl[v] + (1e9 if v >= N else 0)), v))
        left = need[:]; lastc = 0.0; lastk = 0.0
        while ready or run:
            while ready and free:
                _, v = heapq.heappop(ready); free -= 1; heapq.heappush(run, (t + d[v] / (sp if v < N or check_speed is None else float(check_speed)), v))
            t, v = heapq.heappop(run); free += 1; fin[v] = t
            if v < N: lastc = max(lastc, t)
            else: lastk = max(lastk, t)
            for u in users[v]:
                left[u] -= 1
                if left[u] == 0: heapq.heappush(ready, (-(bl[u] + (1e9 if u >= N else 0)), u))
        busy = work / sp + cwork / (sp if check_speed is None else float(check_speed))
        print(f"{P:5d} {sp:5.1f} {t / 3600:10.1f} {lastc / 3600:14.1f} {lastk / 3600:12.1f} {busy / 3600:15.0f} {busy / (P * t):11.0%}")
