#!/usr/bin/env python3
"""isolate_decl: export one declaration (with its dependencies) and see how nanoda copes, to turn a failing piece into a small reproduction.

Purpose: tools/uncovered_check.py, the sweep and the long run name declarations that start but never finish in nanoda (rc -6 or -9). This exports just such a declaration with
lean4export (same extra targets as Comparator), keeps the export in scratch/isolate/NAME.export (and a config), and runs nanoda_bin.timing on it once per stack size in --stacks (MiB, default
16,1024) with --threads threads (default 1), each killed after --timeout seconds (default 300). It prints and appends one JSON line per run to results/isolate-decl.jsonl: export size and
seconds, number of declarations, stack MiB, exit code, wall seconds, peak RSS, and the declarations that began but did not end (from NANODA_DECL_TIMES). Run where the module is built.
Usage: isolate_decl.py NAME MODULE DECL [DECL ...] [--stacks 16,1024] [--threads 1] [--timeout 300]
"""
import os, sys, json, time, subprocess, resource
base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')); root = base + '/src/lean'
args = sys.argv[1:]; opt = lambda k, d: args[args.index(k) + 1] if k in args else d
pos = [a for i, a in enumerate(args) if not a.startswith('--') and (i == 0 or not args[i - 1].startswith('--'))]
name, module, decls = pos[0], pos[1], pos[2:]; stacks = [int(x) for x in opt('--stacks', '16,1024').split(',')]; threads = int(opt('--threads', '1')); tmo = opt('--timeout', '300')
D = base + '/scratch/isolate'; os.makedirs(D, exist_ok=True)
env = dict(os.environ, PATH=f"{base}/ext/lean4export/.lake/build/bin:{base}/ext/bin:{os.path.expanduser('~')}/.elan/bin:{os.environ['PATH']}")
EXTRA = ['Quot', 'Quot.mk', 'Quot.lift', 'Quot.ind', 'propext', 'Quot.sound', 'Classical.choice', 'Nat.add', 'Nat.sub', 'Nat.mul', 'Nat.pow', 'Nat.gcd', 'Nat.div', 'Nat.mod', 'Nat.beq', 'Nat.ble',
         'Nat.land', 'Nat.lor', 'Nat.xor', 'Nat.shiftLeft', 'Nat.shiftRight', 'String.ofList', 'Char.ofNat', 'List', 'eagerReduce', 'Nat', 'String', 'String.mk', 'Char', 'optParam', 'autoParam', 'semiOutParam', 'outParam']
exp = f'{D}/{name}.export'; t = time.time()
with open(exp, 'wb') as f: p = subprocess.run(['lake', 'env', 'lean4export', module, '--', *decls, *EXTRA], cwd=root, env=env, stdout=f, stderr=subprocess.PIPE, text=True)
rec0 = dict(name=name, module=module, decls=decls, export_rc=p.returncode, export_s=round(time.time() - t, 1), export_bytes=os.path.getsize(exp))
print(rec0, flush=True)
if p.returncode: sys.exit(p.stderr[-300:])
cfg = f'{D}/{name}.json'; json.dump(dict(use_stdin=False, export_file_path=exp, permitted_axioms=['propext', 'Quot.sound', 'Classical.choice'], unpermitted_axiom_hard_error=True, num_threads=threads, nat_extension=True, string_extension=True), open(cfg, 'w'))
for mb in stacks:
    tf = f'{D}/{name}.{mb}.times'; r0 = resource.getrusage(resource.RUSAGE_CHILDREN); t = time.time()
    pr = subprocess.Popen(['timeout', '-s', 'KILL', tmo, base + '/ext/bin/nanoda_bin.timing', cfg], env=dict(env, NANODA_STACK_MB=str(mb), NANODA_DECL_TIMES=tf), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _, status, ru = os.wait4(pr.pid, 0); wall = time.time() - t; rc = os.waitstatus_to_exitcode(status)
    b, e = {}, set()
    if os.path.exists(tf):
        for l in open(tf, errors='replace'):
            q = l.rstrip('\n').split('\t')
            if q[0] == 'B': b[q[1]] = q[4]
            elif q[0] == 'E': e.add(q[1])
    rec = dict(rec0, stack_mb=mb, threads=threads, nanoda_rc=rc, wall_s=round(wall, 1), rss_gib=round(ru.ru_maxrss / 2**20, 2), declarations=len(e), unfinished=[v for k, v in b.items() if k not in e][:6], tail=(pr.stdout.read() + pr.stderr.read())[-200:])
    open(base + '/results/isolate-decl.jsonl', 'a').write(json.dumps(rec) + '\n'); print(rec, flush=True)
