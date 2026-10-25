#!/usr/bin/env python3
"""nanoda_let_pr_resources: build small `let` test exports for nanoda's test suite and for the Lean Kernel Arena.

Purpose: nanoda_lib issue 62 and the PR that makes infer_let check a let body with a free variable that has a value, as Lean's kernel does. The tests in
tools/nanoda_let_tests.py use 1 MB exports (Nat and decide machinery); these use only Bool, Eq and True. This compiles tools/nanoda_let_tests/LetPR.lean
with the Lean toolchain of src/lean, exports chosen theorems with lean4export, and builds ill-typed variants by replacing one let value with `false`
(the proofs need `true`):
  siblings     the second of two sibling `let b : Bool` (theorem let_siblings);
  shadow       the inner of two shadowing `let b : Bool` (let_shadow);
  decls        the let in the second of two declarations with the same let shape (let_decl_b);
  value_type   (nanoda only) the unused `let u : Bool` gets the value `True.intro`, of type True. The Arena already has this situation as
               corner-cases/let-value-type-mismatch, with outcome `either`, since substituting the value removes the mismatch.
A checker that mixed up lets of the same name and type would accept the first three.

Modes:
  nanoda OUTDIR   one export of the same-name theorems (positive) plus, per variant, an export of just the declarations it needs, with configs whose\n                  paths are test_resources/Let/NAME.export;
  arena OUTDIR    per variant, an export of just the declarations it needs (as Arena `file` tests, outcome reject), named let-same-name-NAME.ndjson.
With --check NANODA_BIN ..., each binary also runs on each export and the result is printed as PASS or FAIL.
Usage: nanoda_let_pr_resources.py {nanoda|arena} OUTDIR [--check NANODA_BIN ...]
"""
import os, re, sys, json, subprocess, tempfile
here = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
base = os.environ.get('CHECKOUT', here)   # the checkout holding src/lean and ext/lean4export, if it is not the one with this script
src = os.path.join(here, 'tools/nanoda_let_tests/LetPR.lean')
mode, out_dir = sys.argv[1], os.path.abspath(sys.argv[2])
assert mode in ('nanoda', 'arena'), __doc__
binaries = sys.argv[sys.argv.index('--check') + 1:] if '--check' in sys.argv else []
tc = open(os.path.join(base, 'src/lean/lean-toolchain')).read().strip().replace('/', '--').replace(':', '---')
tcdir = os.path.expanduser('~/.elan/toolchains/' + tc)
exporter = os.path.join(base, 'ext/lean4export/.lake/build/bin/lean4export')
THMS = re.findall(r'^theorem (\S+)', open(src).read(), re.M)
work = tempfile.mkdtemp(prefix='nanoda-let-pr-', dir=os.environ.get('CLAUDE_JOB_DIR', None) and os.environ['CLAUDE_JOB_DIR'] + '/tmp')
subprocess.run([tcdir + '/bin/lean', '-o', work + '/LetPR.olean', src], check=True, capture_output=True, cwd=os.path.dirname(src))
KIDS = {'app': ('fn', 'arg'), 'lam': ('type', 'body'), 'forallE': ('type', 'body'), 'letE': ('type', 'value', 'body'), 'proj': ('struct',)}


class Export:
    """An export of some theorems of LetPR.lean (with their dependencies), and lookups over its nodes."""
    def __init__(self, decls):
        self.lines = subprocess.run([exporter, 'LetPR', '--', *decls], check=True, capture_output=True, text=True,
                                    env=dict(os.environ, LEAN_PATH=f'{work}:{tcdir}/lib/lean')).stdout.splitlines()
        self.names, self.nodes, self.thms = {}, {}, {}
        for l in self.lines:
            o = json.loads(l)
            if 'in' in o: self.names[o['in']] = o
            if 'ie' in o: k = next(x for x in o if x != 'ie'); self.nodes[o['ie']] = (k, o[k])
            if 'thm' in o: self.thms[self.name(o['thm']['name'])] = o['thm']
    def name(self, i):   # dotted string of name id `i`
        o = self.names.get(i)
        if o is None: return ''
        if 'str' in o: return (self.name(o['str']['pre']) + '.' if o['str']['pre'] else '') + o['str']['str']
        return self.name(o['num']['pre']) + '.' + str(o['num']['i'])
    def reach(self, root):
        seen, todo = set(), [root]
        while todo:
            i = todo.pop()
            if i not in seen: seen.add(i); k, v = self.nodes[i]; todo += [v[f] for f in KIDS.get(k, ())]
        return seen
    def lets(self, root): return sum(self.nodes[i][0] == 'letE' for i in self.reach(root))
    def const(self, n):   # the node of constant `n`
        found = [i for i, (k, v) in self.nodes.items() if k == 'const' and self.name(v['name']) == n]
        assert found, f'no constant {n} in the export'
        return min(found)
    def let_where(self, pred, what):   # the one letE node satisfying pred(fields)
        found = [i for i, (k, v) in self.nodes.items() if k == 'letE' and pred(v)]
        assert len(found) == 1, f'expected one let {what}, found {len(found)}'
        return found[0]
    def value_uses(self, c): return lambda v: any(self.nodes[j][0] == 'const' and self.name(self.nodes[j][1]['name']) == c for j in self.reach(v['value']))
    def with_value(self, target, donor):   # the lines with letE node `target` given node `donor` as its value
        assert donor < target, f'node {donor} must come before node {target} in the export'
        out = []
        for l in self.lines:
            o = json.loads(l)
            if o.get('ie') == target: o['letE']['value'] = donor; l = json.dumps(o, separators=(',', ':'))
            out.append(l)
        return out


def variant(e, which):   # the ill-typed lines for variant `which` of export `e`
    false = e.const('Bool.false')
    if which == 'siblings': return e.with_value(e.let_where(e.value_uses('Bool.not'), 'using Bool.not'), false)
    if which == 'shadow': return e.with_value(e.let_where(e.value_uses('Bool.and'), 'using Bool.and'), false)
    if which == 'decls': return e.with_value(e.let_where(e.value_uses('Bool.or'), 'using Bool.or'), false)
    if which == 'value_type': return e.with_value(e.let_where(lambda v: e.name(v['name']) == 'u', 'named u'), e.const('True.intro'))
    raise ValueError(which)

os.makedirs(out_dir, exist_ok=True)
runs = []   # (label, path, expected accept)
DECLS = {'siblings': ['let_values_first', 'let_siblings'], 'shadow': ['let_values_first', 'let_shadow'],
         'decls': ['let_values_first', 'let_decl_a', 'let_decl_b'], 'value_type': ['let_values_first', 'let_unused']}
if mode == 'nanoda':
    e = Export(['let_values_first', 'let_siblings', 'let_shadow', 'let_decl_a', 'let_decl_b'])
    print('lets in each theorem (statement/proof):', ', '.join(f"{t} {e.lets(e.thms[t]['type'])}/{e.lets(e.thms[t]['value'])}" for t in e.thms))
    for v, lines in [('positive', e.lines)] + [(w, variant(Export(DECLS[w]), w)) for w in ('siblings', 'shadow', 'decls', 'value_type')]:
        open(f'{out_dir}/{v}.export', 'w').write('\n'.join(lines) + '\n')
        json.dump({'export_file_path': f'test_resources/Let/{v}.export', 'permitted_axioms': [], 'unpermitted_axiom_hard_error': True,
                   'print_success_message': True}, open(f'{out_dir}/{v}.json', 'w'), indent=2)
        runs.append((v, f'{out_dir}/{v}.export', v == 'positive'))
else:
    for v, decls in DECLS.items():
        if v == 'value_type': continue
        e = Export(decls)
        path = f'{out_dir}/let-same-name-{v}.ndjson'
        open(path, 'w').write('\n'.join(variant(e, v)) + '\n')
        runs.append((v, path, False))
        good = f'{work}/let-same-name-{v}-good.ndjson'   # the unmodified export, checked below as a control
        open(good, 'w').write('\n'.join(e.lines) + '\n')
        runs.append((v + ' (unmodified)', good, True))
for label, path, _ in runs:
    if not label.endswith('(unmodified)'): print(f'wrote {path} ({os.path.getsize(path)} bytes)')
bad = 0
for nb in binaries:
    for label, path, ok in runs:
        cfg = f'{work}/run.json'
        json.dump({'export_file_path': path, 'permitted_axioms': [], 'unpermitted_axiom_hard_error': True}, open(cfg, 'w'))
        p = subprocess.run([nb, cfg], capture_output=True, text=True, timeout=60)
        good = (p.returncode == 0) if ok else (p.returncode == 101)
        bad += not good
        print(f"{'PASS' if good else 'FAIL'} {label:24s} rc={p.returncode} {nb}")
sys.exit(1 if bad else 0)
