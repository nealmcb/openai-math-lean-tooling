#!/usr/bin/env python3
"""uncovered_check: check with nanoda the declarations of modules that no Comparator solution imports (run where those modules are built: the cloud volume).

Purpose: Comparator, and so every nanoda run so far, checks only what the 413 solution theorems reach (88% of the OAI modules, results/solution-coverage.json). This takes
the modules in results/uncovered-modules.txt, in batches of --batch modules: lists the declarations each module defines (tools/list_module_decls.lean), exports them with
lean4export (the same extra targets as Comparator: Quot, primitives, the three standard axioms), and runs nanoda (1 GiB stack, --threads threads, per-declaration times) on the export.
A batch whose name list is too long for one command line is exported in several pieces. One JSON line per piece goes to results/uncovered/RUN.jsonl: modules, declarations named, export
bytes and seconds, nanoda exit code, wall seconds, CPU seconds, peak RSS; exports are deleted after the check; per-declaration times of a failed or slow piece are kept in
results/uncovered/times/. Resumable (pieces already recorded are skipped). --sample N takes N random uncovered modules (seeded) for a pilot that sizes the whole job.
Create results/uncovered/STOP to stop after the running pieces. Run from anywhere; needs src/lean built for the modules and ext/bin/nanoda_bin.timing.
Usage: uncovered_check.py RUN [--sample N] [--batch 50] [--jobs 6] [--threads 8] [--shard I/N]
"""
import os, sys, json, time, random, subprocess, resource, gzip, shutil, concurrent.futures as cf
base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')); root = base + '/src/lean'
run = sys.argv[1]; arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
sample = int(arg('--sample', '0')); batch = int(arg('--batch', '50')); jobs = int(arg('--jobs', '6')); threads = int(arg('--threads', '8')); si, sn = (int(x) for x in arg('--shard', '0/1').split('/'))
R = base + '/results/uncovered'; W = base + '/scratch/uncovered'; os.makedirs(R + '/times', exist_ok=True); os.makedirs(W, exist_ok=True); OUT = f'{R}/{run}.jsonl'
env = dict(os.environ, PATH=f"{base}/ext/lean4export/.lake/build/bin:{base}/ext/bin:{os.path.expanduser('~')}/.elan/bin:{os.environ['PATH']}")
NANODA = base + '/ext/bin/nanoda_bin.timing'
EXTRA = ['Quot', 'Quot.mk', 'Quot.lift', 'Quot.ind', 'propext', 'Quot.sound', 'Classical.choice', 'Nat.add', 'Nat.sub', 'Nat.mul', 'Nat.pow', 'Nat.gcd', 'Nat.div', 'Nat.mod', 'Nat.beq', 'Nat.ble',
         'Nat.land', 'Nat.lor', 'Nat.xor', 'Nat.shiftLeft', 'Nat.shiftRight', 'String.ofList', 'Char.ofNat', 'List', 'eagerReduce', 'Nat', 'String', 'String.mk', 'Char', 'optParam', 'autoParam', 'semiOutParam', 'outParam']
mods = [m for m in open(base + '/results/uncovered-modules.txt').read().split() if m != 'OAI']   # the root imports everything; its own declarations are none
if sample: random.Random(1).shuffle(mods); mods = sorted(mods[:sample])
batches = [mods[i:i + batch] for i in range(0, len(mods), batch)]; batches = [b for i, b in enumerate(batches) if i % sn == si]
done = set(json.loads(l)['key'] for l in open(OUT)) if os.path.exists(OUT) else set()
log = lambda m: print(time.strftime('%H:%M:%S'), m, flush=True)


def sh(cmd, cwd=None, out=None):
    r0 = resource.getrusage(resource.RUSAGE_CHILDREN); t = time.time()
    p = subprocess.run(cmd, cwd=cwd, env=env, stdout=out or subprocess.PIPE, stderr=subprocess.PIPE, text=out is None)
    r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    return p, time.time() - t, r1.ru_utime - r0.ru_utime + r1.ru_stime - r0.ru_stime


def do(bi, b, tag=None):
    if os.path.exists(R + '/STOP'): return
    tag = tag or f'{run}-{si}of{sn}-b{bi}'
    p, _, _ = sh(['lake', 'env', 'lean', '--run', base + '/tools/list_module_decls.lean', *b], cwd=root)
    names = [l.split('\t')[1] for l in p.stdout.splitlines() if '\t' in l]
    if not names and 'already contains' in p.stderr and len(b) > 1:   # modules that declare the same name cannot be imported together: split the batch
        h = len(b) // 2; do(bi, b[:h], tag + 'a'); do(bi, b[h:], tag + 'b'); return
    if not names:
        open(OUT, 'a').write(json.dumps(dict(key=tag, modules=len(b), decls=0, err=p.stderr[-300:])) + '\n'); return
    pieces, cur, size = [], [], 0
    for n in names:
        if size + len(n) + 1 > 1_000_000: pieces.append(cur); cur, size = [], 0
        cur.append(n); size += len(n) + 1
    pieces.append(cur)
    for pi, pn in enumerate(pieces):
        key = f'{tag}p{pi}'
        if key in done: continue
        exp = f'{W}/{key}.export'
        with open(exp, 'wb') as f: pe, ews, _ = sh(['lake', 'env', 'lean4export', *b, '--', *pn, *EXTRA], cwd=root, out=f)
        rec = dict(key=key, modules=len(b), first_module=b[0], decls=len(pn), export_rc=pe.returncode, export_s=round(ews, 1), export_bytes=os.path.getsize(exp))
        if pe.returncode == 0 and rec['export_bytes'] > 0:
            cj = f'{W}/{key}.json'; tf = f'{W}/{key}.times'
            json.dump(dict(use_stdin=False, export_file_path=exp, permitted_axioms=['propext', 'Quot.sound', 'Classical.choice'], unpermitted_axiom_hard_error=True, num_threads=threads, nat_extension=True, string_extension=True), open(cj, 'w'))
            env2 = dict(env, NANODA_STACK_MB='1024', NANODA_DECL_TIMES=tf); t = time.time()
            pr = subprocess.Popen(['timeout', '-s', 'KILL', '7200', NANODA, cj], env=env2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            _, status, ru = os.wait4(pr.pid, 0); wall = time.time() - t; rc = os.waitstatus_to_exitcode(status)
            out = (pr.stdout.read() + pr.stderr.read())[-300:]
            rec.update(nanoda_rc=rc, nanoda_wall_s=round(wall, 1), nanoda_cpu_s=round(ru.ru_utime + ru.ru_stime, 1), nanoda_rss_gib=round(ru.ru_maxrss / 2**20, 2), nanoda_tail=out if rc else '')
            if os.path.exists(tf):
                if rc != 0 or wall > 120: subprocess.run(['gzip', '-c', tf], stdout=open(f'{R}/times/{key}.times.gz', 'wb'))
                os.remove(tf)
            os.remove(cj)
        else: rec['export_err'] = pe.stderr[-300:]
        os.remove(exp)
        open(OUT, 'a').write(json.dumps(rec) + '\n'); log(f"{key}: {rec['decls']} decls, export {rec['export_bytes'] / 1e6:.0f} MB in {rec['export_s']} s, nanoda rc {rec.get('nanoda_rc')} {rec.get('nanoda_wall_s')} s")


log(f"{len(mods)} modules in {len(batches)} batches, {jobs} at a time, nanoda {threads} threads")
with cf.ThreadPoolExecutor(jobs) as ex: list(ex.map(lambda x: do(*x), enumerate(batches)))
log('done')
