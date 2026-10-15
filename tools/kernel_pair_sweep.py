#!/usr/bin/env python3
"""kernel_pair_sweep: Lean's kernel and nanoda on the same export, one configuration after another, on this machine.

Purpose: the paired comparison of the two kernels (REPORT.md, nanoda section): for each Comparator configuration, make the solution export once (lean4export, the same targets
Comparator passes), time Lean's own kernel replaying it (the `replaytime` executable of the patched Comparator, ext/comparator-skip: parse time and Environment.replay time, the
same work as Comparator's built-in step) and time nanoda (the timing build, 4 threads like Comparator, 1 GiB checker stack) on the identical file, then delete the export. One JSON line per
configuration goes to results/kernel-pair-sweep.jsonl: export size and time, Lean parse/replay milliseconds and verdict, nanoda wall/CPU seconds, peak memory, exit code and verdict, the number of
declarations, and the machine load at the start of each stage, so a noisy sample can be spotted. Each stage runs in its own transient systemd unit with MemoryMax and no swap, so a runaway
nanoda cannot take the desktop with it (the process is killed and recorded). A stage starts only when MemAvailable is large enough. Resumable (configurations already recorded are skipped). Run
several shards at once with --shard I/N; the order is the laptop's recorded check time, smallest first, so a stop at any point leaves the small and medium sizes done. Skips configurations in
--skip (default: those whose laptop check took over 2000 s, and the three whose nanoda check does not terminate: Catalan, UniqueGamesTheorem, DirectedFeedback). Create results/kernel-pair-sweep.STOP to stop
after the current configuration. Per-declaration nanoda times of slow or failed runs are kept in results/kernel-pair-sweep-times/.
Usage: kernel_pair_sweep.py [--shard 0/2] [--limit N] [--mem 18G] [--min-avail-gib 25] [CONFIG ...]
"""
import os, sys, csv, json, time, subprocess, datetime, shutil, gzip
base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')); root = base + '/src/lean'
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
shard, nshard = (int(x) for x in arg('--shard', '0/1').split('/')); mem = arg('--mem', '18G'); minavail = float(arg('--min-avail-gib', '25')); limit = int(arg('--limit', '0'))
OUT = base + '/results/kernel-pair-sweep.jsonl'; STOP = base + '/results/kernel-pair-sweep.STOP'; W = base + '/scratch/sweep'; TIMES = base + '/results/kernel-pair-sweep-times'
os.makedirs(W, exist_ok=True); os.makedirs(TIMES, exist_ok=True)
QUOT = ['Quot', 'Quot.mk', 'Quot.lift', 'Quot.ind']
PRIM = ['Nat.add', 'Nat.sub', 'Nat.mul', 'Nat.pow', 'Nat.gcd', 'Nat.div', 'Nat.mod', 'Nat.beq', 'Nat.ble', 'Nat.land', 'Nat.lor', 'Nat.xor', 'Nat.shiftLeft',
        'Nat.shiftRight', 'String.ofList', 'Char.ofNat', 'List', 'eagerReduce', 'Nat', 'String', 'String.mk', 'Char', 'optParam', 'autoParam', 'semiOutParam', 'outParam']
env = dict(os.environ, PATH=f"{base}/ext/lean4export/.lake/build/bin:{base}/ext/bin:{os.path.expanduser('~')}/.elan/bin:{os.environ['PATH']}")
REPLAY = base + '/ext/comparator-skip/.lake/build/bin/replaytime'; NANODA = base + '/ext/bin/nanoda_bin.timing'
log = lambda m: print(f"{datetime.datetime.now().astimezone().isoformat(timespec='seconds')} sweep{shard}: {m}", flush=True)


def avail_gib():
    for l in open('/proc/meminfo'):
        if l.startswith('MemAvailable:'): return int(l.split()[1]) / 2**20


def stage(cmd, extra_env=None, cwd=None):
    """Run cmd in a transient unit with a memory cap and no swap, under /usr/bin/time; returns (rc, stdout, wall, user+sys, maxrss GiB, load1, tail of stderr)."""
    while avail_gib() < minavail: time.sleep(20)
    load = os.getloadavg()[0]
    e = [x for kv in (extra_env or {}).items() for x in ('-E', f'{kv[0]}={kv[1]}')]
    full = ['systemd-run', '--user', '--wait', '--pipe', '--collect', f'-p', f'MemoryMax={mem}', '-p', 'MemorySwapMax=0', '-E', f"PATH={env['PATH']}", *e,
            *(['--working-directory=' + cwd] if cwd else []), '/usr/bin/time', '-f', 'TIME %e %U %S %M', *cmd]
    t = time.time(); p = subprocess.run(full, capture_output=True, text=True); wall = time.time() - t
    tl = [l for l in p.stderr.splitlines() if l.startswith('TIME ')]
    if tl: _, w, u, s, m = tl[-1].split(); cpu, rss = float(u) + float(s), int(m) / 2**20
    else: cpu, rss = None, None
    return p.returncode, p.stdout, wall, cpu, rss, load, p.stderr.strip().splitlines()[-3:]


cfgs = {f[:-5]: json.load(open(f'{root}/ComparatorChallenges/{f}')) for f in sorted(os.listdir(root + '/ComparatorChallenges')) if f.endswith('.json')}
laptop = {r['config']: float(r['check_active_s']) for r in csv.DictReader(open(base + '/results/cmp-all/configs.csv')) if r['check_active_s']}
skip = {c for c, v in laptop.items() if v > 2000} | {'Catalan', 'UniqueGamesTheorem', 'DirectedFeedback'}
done = {json.loads(l)['config'] for l in open(OUT)} if os.path.exists(OUT) else set()
names = [c for c in sorted(cfgs, key=lambda c: laptop.get(c, 0)) if c not in skip and c not in done]
names = [c for i, c in enumerate(names) if i % nshard == shard] if not [a for a in sys.argv[1:] if a in cfgs] else [a for a in sys.argv[1:] if a in cfgs]
if limit: names = names[:limit]
log(f"{len(names)} configurations to do (shard {shard}/{nshard}), memory cap {mem}")
for n in names:
    if os.path.exists(STOP): log('STOP file present; exiting'); break
    c = cfgs[n]; exp = f'{W}/{n}.export'; rec = dict(config=n, laptop_check_s=laptop.get(n), started=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'))
    targets = QUOT + c['theorem_names'] + c.get('permitted_axioms', []) + PRIM + (c.get('definition_names') or [])
    rc, _, wall, cpu, rss, load, err = stage(['bash', '-c', f'cd {root} && lake env lean4export {c["solution_module"]} -- ' + ' '.join(targets) + f' > {exp}'])
    rec.update(export_rc=rc, export_s=round(wall, 1), export_rss_gib=rss and round(rss, 2), export_load=round(load, 1), export_bytes=os.path.getsize(exp) if os.path.exists(exp) else 0)
    if rc == 0 and rec['export_bytes'] > 0:
        rc, out, wall, cpu, rss, load, err = stage([REPLAY, exp])
        parsed = [l for l in out.splitlines() if l.startswith('parsed in')]; verdict = [l for l in out.splitlines() if 'Lean kernel' in l]
        rec.update(lean_rc=rc, lean_wall_s=round(wall, 1), lean_cpu_s=cpu and round(cpu, 1), lean_rss_gib=rss and round(rss, 2), lean_load=round(load, 1),
                   lean_parse_ms=int(parsed[0].split()[2]) if parsed else None, lean_replay_ms=int(verdict[-1].split('replay ')[1].split()[0]) if verdict and 'replay ' in verdict[-1] else None,
                   lean_verdict=(verdict[-1][:80] if verdict else None))
        cfgp = f'{W}/{n}.json'; json.dump(dict(use_stdin=False, export_file_path=exp, permitted_axioms=c.get('permitted_axioms', []), unpermitted_axiom_hard_error=True, num_threads=4,
                                              nat_extension=True, string_extension=True), open(cfgp, 'w'))
        tf = f'{W}/{n}.times'
        rc, out, wall, cpu, rss, load, err = stage([NANODA, cfgp], {'NANODA_STACK_MB': '1024', 'NANODA_DECL_TIMES': tf})
        decl = None
        if os.path.exists(tf):
            decl = sum(1 for l in open(tf, errors='replace') if l.startswith('E\t'))
            if wall > 60 or rc != 0: shutil.copy(tf, f'{TIMES}/{n}.times'); subprocess.run(['gzip', '-f', f'{TIMES}/{n}.times'])
            os.remove(tf)
        rec.update(nanoda_rc=rc, nanoda_wall_s=round(wall, 1), nanoda_cpu_s=cpu and round(cpu, 1), nanoda_rss_gib=rss and round(rss, 2), nanoda_load=round(load, 1), nanoda_decls=decl, nanoda_err=err[-2:] if rc else None)
    for f in (exp, f'{W}/{n}.json'):
        if os.path.exists(f): os.remove(f)
    open(OUT, 'a').write(json.dumps(rec) + '\n')
    log(f"{n}: export {rec['export_bytes'] / 1e6:.0f} MB in {rec['export_s']} s; Lean replay {rec.get('lean_replay_ms')} ms; nanoda {rec.get('nanoda_wall_s')} s (rc {rec.get('nanoda_rc')})")
log('done')
