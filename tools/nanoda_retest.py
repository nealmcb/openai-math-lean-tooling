#!/usr/bin/env python3
"""nanoda_retest: re-run the configurations that failed in nanoda with another nanoda build, e.g. a newer upstream master.

Purpose: nanoda_lib issue 55 reports configurations that Lean's kernel accepts and nanoda aborts on (stack overflow, 2^31-entry index panic). The maintainer asked whether the latest master still fails
(it has new bignum and Nat handling). This exports each failing configuration's solution once with lean4export (the same targets as Comparator and tools/kernel_pair_sweep.py), runs the given
nanoda_bin on it (4 threads, as Comparator does), and appends one JSON line per run to results/nanoda-retest.jsonl: nanoda commit and path, export size and seconds, exit code, wall and CPU seconds, peak RSS and the last
output lines. Each stage runs in a transient systemd unit with a memory cap and no swap, so a runaway nanoda cannot take the desktop with it (it is killed and recorded), and a wall-clock timeout.
Exports are deleted after the run unless --keep. The default configurations are the 15 that fail with the pinned nanoda; the ones whose closure is not built on this machine (the Laughlin family) are skipped with a note.
Usage: nanoda_retest.py --nanoda PATH [--mem 30G] [--timeout 1800] [--threads 4] [--keep] [CONFIG ...]
"""
import os, sys, json, time, subprocess, datetime
base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')); root = base + '/src/lean'
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
NANODA = os.path.abspath(arg('--nanoda', base + '/ext/bin/nanoda_bin')); mem = arg('--mem', '30G'); tmo = int(arg('--timeout', '1800')); threads = int(arg('--threads', '4')); keep = '--keep' in sys.argv
DEFAULT = ['BinPackingGap', 'VertexCover', 'IndependentSets', 'MinUncut', 'PerfectCompleteness', 'OptimalMaxCut', 'KMedianThreshold', 'SquareDifference', 'ContinuumCoulombHardness',
           'DirectedFeedback', 'UniqueGamesTheorem', 'Catalan']
names = [a for a in sys.argv[1:] if os.path.exists(f'{root}/ComparatorChallenges/{a}.json')] or DEFAULT
QUOT = ['Quot', 'Quot.mk', 'Quot.lift', 'Quot.ind']
PRIM = ['Nat.add', 'Nat.sub', 'Nat.mul', 'Nat.pow', 'Nat.gcd', 'Nat.div', 'Nat.mod', 'Nat.beq', 'Nat.ble', 'Nat.land', 'Nat.lor', 'Nat.xor', 'Nat.shiftLeft',
        'Nat.shiftRight', 'String.ofList', 'Char.ofNat', 'List', 'eagerReduce', 'Nat', 'String', 'String.mk', 'Char', 'optParam', 'autoParam', 'semiOutParam', 'outParam']
env = dict(os.environ, PATH=f"{base}/ext/lean4export/.lake/build/bin:{os.path.expanduser('~')}/.elan/bin:{os.environ['PATH']}")
W = base + '/scratch/retest'; os.makedirs(W, exist_ok=True); OUT = base + '/results/nanoda-retest.jsonl'
try:
    d = os.path.dirname(os.path.dirname(os.path.dirname(NANODA)))   # .../target/release/nanoda_bin -> source tree
    commit = subprocess.run(['git', '-C', d, 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip() or None
except Exception: commit = None


def stage(cmd, extra=None):
    full = ['systemd-run', '--user', '--wait', '--pipe', '--collect', '-p', f'MemoryMax={mem}', '-p', 'MemorySwapMax=0', '-p', f'RuntimeMaxSec={tmo}', '-E', f"PATH={env['PATH']}",
            *[x for k, v in (extra or {}).items() for x in ('-E', f'{k}={v}')], '/usr/bin/time', '-f', 'TIME %e %U %S %M', *cmd]
    t = time.time(); p = subprocess.run(full, capture_output=True, text=True); wall = time.time() - t
    tl = [l for l in p.stderr.splitlines() if l.startswith('TIME ')]
    cpu, rss = (float(tl[-1].split()[2]) + float(tl[-1].split()[3]), int(tl[-1].split()[4]) / 2**20) if tl else (None, None)
    return p, wall, cpu, rss


for n in names:
    c = json.load(open(f'{root}/ComparatorChallenges/{n}.json')); exp = f'{W}/{n}.export'
    rec = dict(config=n, nanoda=NANODA, nanoda_commit=commit, threads=threads, mem_cap=mem, timeout_s=tmo, started=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'))
    targets = QUOT + c['theorem_names'] + c.get('permitted_axioms', []) + PRIM + (c.get('definition_names') or [])
    p, wall, cpu, rss = stage(['bash', '-c', f'cd {root} && lake env lean4export {c["solution_module"]} -- ' + ' '.join(targets) + f' > {exp}'])
    rec.update(export_rc=p.returncode, export_s=round(wall, 1), export_bytes=os.path.getsize(exp) if os.path.exists(exp) else 0)
    if p.returncode == 0 and rec['export_bytes'] > 0:
        cfg = f'{W}/{n}.json'
        json.dump(dict(use_stdin=False, export_file_path=exp, permitted_axioms=c.get('permitted_axioms', []), unpermitted_axiom_hard_error=True, num_threads=threads, nat_extension=True, string_extension=True), open(cfg, 'w'))
        p, wall, cpu, rss = stage([NANODA, cfg])
        rec.update(nanoda_rc=p.returncode, wall_s=round(wall, 1), cpu_s=cpu and round(cpu, 1), rss_gib=rss and round(rss, 2), tail=(p.stdout + p.stderr).strip().splitlines()[-3:])
        os.remove(cfg)
    else: rec['note'] = 'export failed (closure not built on this machine?): ' + p.stderr.strip()[-200:]
    if os.path.exists(exp) and not keep: os.remove(exp)
    open(OUT, 'a').write(json.dumps(rec) + '\n'); print(json.dumps({k: rec.get(k) for k in ('config', 'nanoda_commit', 'export_bytes', 'nanoda_rc', 'wall_s', 'rss_gib')}), flush=True)
