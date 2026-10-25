#!/usr/bin/env python3
"""nanoda_let_tests: check that nanoda builds accept well-typed `let` terms and reject ill-typed ones, using exports of small theorems.

Purpose: nanoda_lib issue 62. The fix changes how the type checker's infer_let handles the bound variable (a free variable with a value, unfolded lazily, as
Lean's kernel does) and nanoda's own test suite barely exercises `let`; the risk to rule out is a build that accepts what it should reject. This compiles
tools/nanoda_let_tests/LetTests.lean with the Lean toolchain of src/lean and exports every theorem in it with lean4export. Variants:
  positive          the export as is (every theorem well-typed; the `sorry` probes only load because sorryAx is permitted): must be accepted;
  FOO_bad           for each pair FOO / FOO_bad in the file, FOO's proof given FOO_bad's false statement: must be rejected. The pairs cover substitution
                    into arithmetic, sibling and shadowing lets with the same name and type, a let-bound function, a value mentioning an outer bound
                    variable, a dependent type, a let inside a type, and two declarations with identically shaped lets (state carried over would show);
  let_sibv_value, let_shadowv_value  in let_sibv (sibling lets) and let_shadowv (shadowing lets), whose proofs need the variable's value to type-check,\n                    the let with value 55 or 66 given the value 1: must be rejected; a checker confusing two lets of the same name and type accepts them;\n  value_type        in let_vty the value of the inner let `vtyx : Nat` replaced by the Bool value of the outer `vtyb`: must be rejected (the\n                    value-against-annotation check).
Each ill-typed export holds exactly one wrong declaration, moved to the end of the file. Every given nanoda binary runs on every export (1 thread, 60 s
limit); a rejection counts only if nanoda fails an assertion (exit 101), not on a timeout or crash. Prints PASS or FAIL per run, and first the\nnumber of let nodes reachable from each theorem's statement and proof (lean4export shares nodes and ignores binder names, so this checks that every test\nreally contains its lets).
Usage: nanoda_let_tests.py NANODA_BIN [NANODA_BIN ...]
"""
import os, re, sys, json, subprocess, tempfile
here = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
base = os.environ.get('CHECKOUT', here)   # the checkout holding src/lean and ext/lean4export, if it is not the one with this script
src = os.path.join(here, 'tools/nanoda_let_tests/LetTests.lean')
tc = open(os.path.join(base, 'src/lean/lean-toolchain')).read().strip().replace('/', '--').replace(':', '---')
tcdir = os.path.expanduser('~/.elan/toolchains/' + tc)
exporter = os.path.join(base, 'ext/lean4export/.lake/build/bin/lean4export')
THMS = re.findall(r'^theorem (\S+)', open(src).read(), re.M)
PRIM = ['Quot', 'Quot.mk', 'Quot.lift', 'Quot.ind', 'Nat.add', 'Nat.sub', 'Nat.mul', 'Nat.pow', 'Nat.gcd', 'Nat.div', 'Nat.mod', 'Nat.beq', 'Nat.ble', 'Nat.land', 'Nat.lor',
        'Nat.xor', 'Nat.shiftLeft', 'Nat.shiftRight', 'String.ofList', 'Char.ofNat', 'List', 'eagerReduce', 'Nat', 'String', 'String.mk', 'Char', 'optParam', 'autoParam',
        'semiOutParam', 'outParam', 'propext', 'Quot.sound', 'Classical.choice']
work = tempfile.mkdtemp(prefix='nanoda-let-tests-', dir=os.environ.get('CLAUDE_JOB_DIR', None) and os.environ['CLAUDE_JOB_DIR'] + '/tmp')
subprocess.run([tcdir + '/bin/lean', '-o', work + '/LetTests.olean', src], check=True, capture_output=True, cwd=os.path.dirname(src))   # lean wants the file under its working directory
exp = subprocess.run([exporter, 'LetTests', '--', *THMS, *PRIM], check=True, capture_output=True, text=True,
                     env=dict(os.environ, LEAN_PATH=f'{work}:{tcdir}/lib/lean')).stdout.splitlines()
names, thms = {}, {}
for l in exp:
    o = json.loads(l)
    if 'str' in o and 'in' in o and o['str']['pre'] == 0: names[o['str']['str']] = o['in']
    if 'thm' in o: thms[o['thm']['name']] = o['thm']
def with_thm(exp, name, **fields):   # same export, one theorem's fields replaced; moved to the end, where every expression it can refer to is defined
    out, moved = [], None
    for l in exp:
        o = json.loads(l)
        if 'thm' in o and o['thm']['name'] == names[name]: o['thm'].update(fields); moved = json.dumps(o, separators=(',', ':'))
        else: out.append(l)
    return out + [moved]
KIDS = {'app': ('fn', 'arg'), 'lam': ('type', 'body'), 'forallE': ('type', 'body'), 'letE': ('type', 'value', 'body'), 'proj': ('struct',)}
nodes = {}
for l in exp:
    o = json.loads(l)
    if 'ie' in o: k = next(x for x in o if x != 'ie'); nodes[o['ie']] = (k, o[k])
def lets_in(root):   # number of distinct letE nodes reachable from expression `root`
    seen, todo, n = set(), [root], 0
    while todo:
        i = todo.pop()
        if i in seen: continue
        seen.add(i); k, v = nodes[i]; n += k == 'letE'
        todo += [v[f] for f in KIDS.get(k, ())]
    return n
print('letE nodes reachable from each theorem (statement/proof):', ', '.join(f"{t} {lets_in(thms[names[t]]['type'])}/{lets_in(thms[names[t]]['value'])}" for t in THMS if not t.endswith('_bad')))
def reach(root):   # ids of the expression nodes reachable from `root`
    seen, todo = set(), [root]
    while todo:
        i = todo.pop()
        if i not in seen: seen.add(i); k, v = nodes[i]; todo += [v[f] for f in KIDS.get(k, ())]
    return seen
def let_with_literal(lit, unique=True):   # the letE node whose value contains the Nat literal `lit` (the one with the smallest value if not unique)
    found = [i for i, (k, v) in nodes.items() if k == 'letE' and any(nodes[j] == ('natVal', str(lit)) for j in reach(v['value']))]
    assert found and (len(found) == 1 or not unique), f'expected exactly one let with literal {lit} in its value, found {len(found)}'
    return min(found, key=lambda i: len(reach(nodes[i][1]['value'])))
def with_let_value_from(exp, target, donor):   # letE node `target` gets the value of letE node `donor`
    out = []
    for l in exp:
        o = json.loads(l)
        if o.get('ie') == target: o['letE']['value'] = nodes[donor][1]['value']; l = json.dumps(o, separators=(',', ':'))
        out.append(l)
    return out
def with_inner_let_value(exp, outer):   # the let directly inside the let binding `outer` gets `outer`'s value (lets are found by position: binder names are not part of node identity)
    o_let = next(v for k, v in nodes.values() if k == 'letE' and v['name'] == names[outer])
    target = o_let['body']
    assert nodes[target][0] == 'letE', 'the body of the outer let is not a let'
    out = []
    for l in exp:
        o = json.loads(l)
        if o.get('ie') == target: o['letE']['value'] = o_let['value']; l = json.dumps(o, separators=(',', ':'))
        out.append(l)
    return out
variants = {'positive': (exp, True)}
for t in THMS:
    if t + '_bad' in THMS: variants[t + '_bad'] = (with_thm(exp, t, type=thms[names[t + '_bad']]['type']), False)
variants['value_type'] = (with_inner_let_value(exp, 'vtyb'), False)
one = let_with_literal(1, unique=False)   # `let x : Nat := 1` (let_sib, let_xd1)
for t, lit in (('let_sibv', 55), ('let_shadowv', 66)): variants[t + '_value'] = (with_let_value_from(exp, let_with_literal(lit), one), False)
for v, (lines, _) in variants.items():
    open(f'{work}/{v}.export', 'w').write('\n'.join(lines) + '\n')
    json.dump(dict(use_stdin=False, export_file_path=f'{work}/{v}.export', permitted_axioms=['propext', 'Quot.sound', 'Classical.choice', 'sorryAx'],
                   unpermitted_axiom_hard_error=True, num_threads=1, nat_extension=True, string_extension=True), open(f'{work}/{v}.json', 'w'))
def label(nb):   # .../TREE/target/release/nanoda_bin -> TREE; .../target-NAME/release/nanoda_bin -> target-NAME
    d = os.path.dirname(os.path.dirname(os.path.abspath(nb)))
    return os.path.basename(d) if os.path.basename(d) != 'target' else os.path.basename(os.path.dirname(d))
bad = 0
for nb in sys.argv[1:]:
    for v, (_, ok) in variants.items():
        try: p = subprocess.run([nb, f'{work}/{v}.json'], capture_output=True, text=True, timeout=60); rc = p.returncode; el = p.stderr.strip().splitlines(); err = next((el[i + 1] for i, x in enumerate(el[:-1]) if 'panicked at' in x), el[-1] if el else '')[:100]
        except subprocess.TimeoutExpired: rc, err = 'timeout', ''
        good = (rc == 0) if ok else (rc == 101)
        bad += not good
        print(f"{'PASS' if good else 'FAIL'} {v:22s} rc={rc} {label(nb)} {err}")
sys.exit(1 if bad else 0)
