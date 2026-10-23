#!/usr/bin/env python3
"""nanoda_ab: run several nanoda builds on the same Comparator configurations, exporting each solution once, and record every run.

Purpose: compare nanoda builds (for example upstream master before and after a pull request, nanoda_lib PR 59) on correctness and cost on the same machine: whether anything that passed
now fails, whether the 15 configurations that failed with the pinned build pass, and how wall time, CPU time and peak memory change. For each configuration it exports the solution once
with lean4export (the same targets as Comparator and tools/nanoda_retest.py), runs every build on that export in the order given, deletes the export, and appends one JSON line per
(configuration, build) to the output file: label, commit of the build's source tree, export size and seconds, threads, exit code, wall and CPU seconds, peak RSS and the last output
lines. Each stage runs in a transient systemd unit with a memory cap, no swap and a runtime limit. Configurations run JOBS at a time, in the order given (put the largest first).
Needs the closure of every solution built under src/lean (restore it from the Lake cache with tools/restore_ir_for.py --from-cache, or use a machine with the full build).
Usage: nanoda_ab.py --build LABEL=PATH [--build LABEL=PATH ...] [--jobs 4] [--threads 4] [--mem 30G] [--timeout 3600] [--out results/nanoda-ab.jsonl] CONFIG [CONFIG ...]
       (CONFIG may also be @FILE, one configuration name per line)
"""
import os, sys, json, time, subprocess, datetime, threading
from concurrent.futures import ThreadPoolExecutor
base = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')); root = base + '/src/lean'
builds, names, opt, i, a = [], [], {'--jobs': '4', '--threads': '4', '--mem': '30G', '--timeout': '3600', '--out': base + '/results/nanoda-ab.jsonl'}, 0, sys.argv[1:]
while i < len(a):
    if a[i] == '--build': label, path = a[i + 1].split('=', 1); builds.append((label, os.path.abspath(path))); i += 2
    elif a[i] in opt: opt[a[i]] = a[i + 1]; i += 2
    elif a[i].startswith('@'): names += [l.strip() for l in open(a[i][1:]) if l.strip()]; i += 1
    else: names.append(a[i]); i += 1
QUOT = ['Quot', 'Quot.mk', 'Quot.lift', 'Quot.ind']
PRIM = ['Nat.add', 'Nat.sub', 'Nat.mul', 'Nat.pow', 'Nat.gcd', 'Nat.div', 'Nat.mod', 'Nat.beq', 'Nat.ble', 'Nat.land', 'Nat.lor', 'Nat.xor', 'Nat.shiftLeft',
        'Nat.shiftRight', 'String.ofList', 'Char.ofNat', 'List', 'eagerReduce', 'Nat', 'String', 'String.mk', 'Char', 'optParam', 'autoParam', 'semiOutParam', 'outParam']
env_path = f"{base}/ext/lean4export/.lake/build/bin:{os.path.expanduser('~')}/.elan/bin:{os.environ['PATH']}"
W = base + '/scratch/ab'; os.makedirs(W, exist_ok=True); lock = threading.Lock()
def commit_of(binpath):
    d = binpath
    for _ in range(4):
        d = os.path.dirname(d)
        if os.path.exists(os.path.join(d, 'Cargo.toml')):
            return subprocess.run(['git', '-C', d, 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip() or None
    return None
commits = {label: commit_of(path) for label, path in builds}
def stage(cmd):
    full = ['systemd-run', '--user', '--wait', '--pipe', '--collect', '-p', f"MemoryMax={opt['--mem']}", '-p', 'MemorySwapMax=0', '-p', f"RuntimeMaxSec={opt['--timeout']}", '-E', f'PATH={env_path}',
            '/usr/bin/time', '-f', 'TIME %e %U %S %M', *cmd]
    t = time.time(); p = subprocess.run(full, capture_output=True, text=True); wall = time.time() - t
    tl = [l for l in p.stderr.splitlines() if l.startswith('TIME ')]
    cpu, rss = (float(tl[-1].split()[2]) + float(tl[-1].split()[3]), int(tl[-1].split()[4]) / 2**20) if tl else (None, None)
    return p, wall, cpu, rss
def record(rec):
    with lock:
        open(opt['--out'], 'a').write(json.dumps(rec) + '\n')
        print(json.dumps({k: rec.get(k) for k in ('config', 'label', 'export_bytes', 'rc', 'wall_s', 'rss_gib')}), flush=True)
def one(n):
    c = json.load(open(f'{root}/ComparatorChallenges/{n}.json')); exp = f'{W}/{n}.export'
    targets = QUOT + c['theorem_names'] + c.get('permitted_axioms', []) + PRIM + (c.get('definition_names') or [])
    p, wall, _, _ = stage(['bash', '-c', f'cd {root} && lake env lean4export {c["solution_module"]} -- ' + ' '.join(targets) + f' > {exp}'])
    size = os.path.getsize(exp) if os.path.exists(exp) else 0
    if p.returncode or not size:
        record(dict(config=n, label=None, export_rc=p.returncode, export_bytes=size, note='export failed: ' + p.stderr.strip()[-200:])); return
    cfg = f'{W}/{n}.json'
    json.dump(dict(use_stdin=False, export_file_path=exp, permitted_axioms=c.get('permitted_axioms', []), unpermitted_axiom_hard_error=True, num_threads=int(opt['--threads']),
                   nat_extension=True, string_extension=True), open(cfg, 'w'))
    for label, path in builds:
        started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
        p, w, cpu, rss = stage([path, cfg])
        record(dict(config=n, label=label, commit=commits[label], started=started, threads=int(opt['--threads']), mem_cap=opt['--mem'], export_s=round(wall, 1), export_bytes=size,
                    rc=p.returncode, wall_s=round(w, 1), cpu_s=cpu and round(cpu, 1), rss_gib=rss and round(rss, 2), tail=(p.stdout + p.stderr).strip().splitlines()[-3:]))
    os.remove(cfg); os.remove(exp)
with ThreadPoolExecutor(int(opt['--jobs'])) as ex: list(ex.map(one, names))
