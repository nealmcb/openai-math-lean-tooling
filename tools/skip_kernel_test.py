#!/usr/bin/env python3
"""skip_kernel_test: can a build skip Lean's own kernel and rely on an external checker (nanoda) alone?

Purpose: Lean's elaborator hands every declaration to the C++ kernel, and there is no switch to use another kernel in Lake; but the option
`debug.skipKernelTC` ("skip kernel type checker ... may compromise soundness") makes `lean` add declarations without checking them. If a build
done that way is followed by `lean4export` and a nanoda check of the export, nanoda would be the only kernel in the pipeline. This tests that on
a small module without touching the project's build directory. Everything goes to scratch/skipkernel/ and results/skip-kernel-test/.
Steps (each timed; user+system CPU seconds of the compile from the child's rusage):
  1. copy OAI/Algebra/Universal/GraphCriterion.lean (18 theorems, imports only built modules) to a scratch module and compile it twice with the
     project's built .olean files on LEAN_PATH: normally, and with -D debug.skipKernelTC=true; compare compile time and output sizes;
  2. export the config's theorem (OAI.FiniteCongruence.graph_criterion) from each result with lean4export, check each export with nanoda_bin
     (the config file Comparator writes), and compare the two exports byte for byte;
  3. soundness control: a module that adds `theorem bogus : False := True.intro` through `addDecl`. Compiled normally the kernel must reject it;
     compiled with the skip option it is accepted; its export must then be rejected by nanoda. This shows what is lost (the build no longer
     catches it) and what remains (the external check does).
Prints one line per step and writes results/skip-kernel-test/summary.json (or summary-NAME.json with --module). A second module can be
tried with --module OAI.X.Y (any built module whose imports are built) --theorem FULL.NAME [--theorem ...]; the soundness control then still runs.
Usage: skip_kernel_test.py [--module OAI.Algebra.Universal.GraphCriterion --theorem OAI.FiniteCongruence.graph_criterion]
"""
import os, sys, json, time, subprocess, resource, shutil
base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')); root = base + '/src/lean'
S = base + '/scratch/skipkernel'; R = base + '/results/skip-kernel-test'
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + '/src/SkipTest'); os.makedirs(S + '/lib/SkipTest'); os.makedirs(R, exist_ok=True)
home = os.path.expanduser('~'); tc = f'{home}/.elan/toolchains/leanprover--lean4---v4.34.1'
lp = subprocess.run(['lake', 'env', 'printenv', 'LEAN_PATH'], cwd=root, capture_output=True, text=True).stdout.strip().splitlines()[-1]
env = dict(os.environ, LEAN_PATH=S + '/lib:' + lp, PATH=f"{base}/ext/lean4export/.lake/build/bin:{base}/ext/bin:{tc}/bin:{os.environ['PATH']}")
summary = {}
arg = lambda k: [sys.argv[i + 1] for i, x in enumerate(sys.argv) if x == k]
MODULE = (arg('--module') or ['OAI.Algebra.Universal.GraphCriterion'])[0]; THMS = arg('--theorem') or ['OAI.FiniteCongruence.graph_criterion']
TAG = '' if not arg('--module') else '-' + MODULE.split('.')[-1]


def run(cmd, cwd=None, out=None):
    r0 = resource.getrusage(resource.RUSAGE_CHILDREN); t = time.time()
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    return p, time.time() - t, (r1.ru_utime - r0.ru_utime) + (r1.ru_stime - r0.ru_stime)


def compile_(name, skip):
    cmd = ['lean', *(['-D', 'debug.skipKernelTC=true'] if skip else []), '-R', '.', '-o', f'{S}/lib/SkipTest/{name}.olean', f'SkipTest/{name}.lean']
    return run(cmd, cwd=S + '/src')


def nanoda(export_path):
    cfg = dict(use_stdin=False, export_file_path=export_path, permitted_axioms=['propext', 'Quot.sound', 'Classical.choice'], unpermitted_axiom_hard_error=True,
               num_threads=4, nat_extension=True, string_extension=True)
    json.dump(cfg, open(S + '/nanoda.json', 'w'))
    return run(['nanoda_bin', S + '/nanoda.json'])


def export(mod, names):
    prim = ['Quot', 'Quot.mk', 'Quot.lift', 'Quot.ind', 'Nat.add', 'Nat.sub', 'Nat.mul', 'Nat.pow', 'Nat.gcd', 'Nat.div', 'Nat.mod', 'Nat.beq', 'Nat.ble', 'Nat.land',
            'Nat.lor', 'Nat.xor', 'Nat.shiftLeft', 'Nat.shiftRight', 'String.ofList', 'Char.ofNat', 'List', 'eagerReduce', 'Nat', 'String', 'String.mk', 'Char',
            'optParam', 'autoParam', 'semiOutParam', 'outParam', 'propext', 'Quot.sound', 'Classical.choice']
    p, w, c = run(['lean4export', mod, '--', *names, *prim])
    return p.stdout, w


def line(m): print(m, flush=True)


# 1 and 2: a real module
src = open(root + '/' + MODULE.replace('.', '/') + '.lean').read()
exports = {}
for tag, skip in (('normal', False), ('skip', True)):
    name = 'GC_' + tag; open(f'{S}/src/SkipTest/{name}.lean', 'w').write(src)
    p, wall, cpu = compile_(name, skip)
    ok = p.returncode == 0 and os.path.exists(f'{S}/lib/SkipTest/{name}.olean')
    line(f"compile {tag:6s}: exit {p.returncode}, wall {wall:.1f} s, cpu {cpu:.1f} s, olean {os.path.getsize(f'{S}/lib/SkipTest/{name}.olean') if ok else 0} bytes")
    summary['compile_' + tag] = dict(exit=p.returncode, wall_s=round(wall, 1), cpu_s=round(cpu, 1), err=p.stderr[-300:] + p.stdout[-300:] if p.returncode else '')
    if ok:
        data, w = export('SkipTest.' + name, THMS); open(f'{S}/{name}.export', 'w').write(data); exports[tag] = data
        q, nw, ncpu = nanoda(f'{S}/{name}.export'); text = (q.stdout + q.stderr).strip().splitlines()
        line(f"  export {len(data) / 1e6:.2f} MB in {w:.1f} s; nanoda exit {q.returncode} in {nw:.1f} s: {text[-1] if text else ''}")
        summary['nanoda_' + tag] = dict(exit=q.returncode, wall_s=round(nw, 2), export_bytes=len(data), last=text[-1] if text else '')
if len(exports) == 2:
    same = exports['normal'].replace('GC_normal', 'GC').replace('GraphCriterion', 'GC') == exports['skip'].replace('GC_skip', 'GC')
    line(f"the two exports are {'identical' if exports['normal'] == exports['skip'].replace('GC_skip', 'GC_normal') else 'different'} (module names aside)")
    summary['exports_identical'] = exports['normal'] == exports['skip'].replace('GC_skip', 'GC_normal')

# 3: soundness control
bad = '''import Lean
open Lean Elab Command
run_cmd liftCoreM <| addDecl <| .thmDecl { name := `SkipTest.bogus, levelParams := [], type := mkConst ``False, value := mkConst ``True.intro }
'''
open(S + '/src/SkipTest/Bad_normal.lean', 'w').write(bad); open(S + '/src/SkipTest/Bad_skip.lean', 'w').write(bad)
for tag, skip in (('normal', False), ('skip', True)):
    name = 'Bad_' + tag; p, wall, cpu = compile_(name, skip)
    msg = (p.stdout + p.stderr).strip().splitlines()
    line(f"bogus theorem, compile {tag:6s}: exit {p.returncode}: {msg[0][:150] if msg else 'no message'}")
    summary['bogus_compile_' + tag] = dict(exit=p.returncode, msg=msg[:2])
    if p.returncode == 0:
        data, w = export('SkipTest.' + name, ['SkipTest.bogus']); open(f'{S}/{name}.export', 'w').write(data)
        q, nw, _ = nanoda(f'{S}/{name}.export'); text = (q.stdout + q.stderr).strip().splitlines()
        line(f"  nanoda on the export of `bogus : False`: exit {q.returncode}: {' | '.join(text[-2:])[:200]}")
        summary['bogus_nanoda'] = dict(exit=q.returncode, last=text[-3:])
json.dump(summary, open(R + f'/summary{TAG}.json', 'w'), indent=1)
