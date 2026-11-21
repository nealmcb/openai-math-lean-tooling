#!/usr/bin/env python3
"""lean_source_scan: count, in any Lean source tree, the constructs a successful build does not rule out, and list where they are.

Purpose: a first look at a third-party Lean project before building it (2026-11-20: Levent Alpöge's claimed Lean proof of the
Riemann hypothesis, 175,187 files, alpo.ge/lean.tar.gz.part01..14). A build accepts `sorry` (a warning), new `axiom`s,
`native_decide` (trusted through an extra axiom) and `unsafe`/`implemented_by`/`extern` code, and code that runs at elaboration time
(`run_cmd`, `#eval`, `initialize`, `elab`/`macro` definitions, environment edits such as `modifyEnv`/`addDecl`) can change what a
build appears to have checked. A kernel replay of an export (Comparator, nanoda) settles the named theorems regardless; this only
shows where to look. tools/source_audit.py is the openai/math-specific version. Comments are removed first; strings are not, so
counts are approximate. Prints per-construct totals and up to SHOW example files for each.
Usage: lean_source_scan.py SRC_DIR [SHOW=8]
"""
import os, re, sys
root = sys.argv[1]; show = int(sys.argv[2]) if len(sys.argv) > 2 else 8
cm = re.compile(r'/-.*?-/|--[^\n]*', re.S)
pats = {
    'sorry / admit': r'\bsorry\b|\badmit\b',
    'axiom': r'^\s*(?:@\[[^\]]*\]\s*)?(?:private\s+|protected\s+|noncomputable\s+)*axiom\b',
    'native_decide': r'\bnative_decide\b|decide\s*\+\s*native|Lean\.ofReduceBool',
    'unsafe': r'\bunsafe\b',
    'implemented_by / extern': r'@\[[^\]]*\b(?:implemented_by|extern)\b',
    'opaque': r'^\s*(?:private\s+|protected\s+)?opaque\b',
    'run_cmd / run_elab / run_meta': r'^\s*#?run_(?:cmd|elab|meta)\b',
    '#eval': r'^\s*#eval\b',
    'initialize': r'^\s*(?:builtin_)?initialize\b',
    'elab / macro / syntax defs': r'^\s*(?:@\[[^\]]*\]\s*)?(?:local\s+|scoped\s+)?(?:elab|elab_rules|macro|macro_rules|syntax)\b',
    'environment edits': r'\b(?:modifyEnv|addDecl|addAndCompile|setEnv|replayConstants?)\b',
    'debug / kernel options': r'set_option\s+(?:debug\.\S+|kernel\.\S+|trust)\b',
    'theorem / lemma': r'^\s*(?:@\[[^\]]*\]\s*)?(?:private\s+|protected\s+)?(?:theorem|lemma)\b',
}
cp = {k: re.compile(v, re.M) for k, v in pats.items()}
tot = {k: 0 for k in pats}; files = {k: [] for k in pats}; n = nbytes = 0
for dp, ds, fs in os.walk(root):
    ds.sort()
    for f in sorted(fs):
        if not f.endswith('.lean'): continue
        p = os.path.join(dp, f); t = open(p, encoding='utf-8', errors='replace').read(); n += 1; nbytes += len(t); t = cm.sub(' ', t)
        for k, c in cp.items():
            c_n = len(c.findall(t))
            if c_n: tot[k] += c_n; files[k].append((os.path.relpath(p, root), c_n))
print(f'{root}: {n} .lean files, {nbytes / 1e9:.2f} GB')
for k in pats:
    print(f'{k:32s} {tot[k]:9d} occurrences in {len(files[k]):7d} files')
    if k != 'theorem / lemma':
        for p, c in sorted(files[k], key=lambda x: -x[1])[:show]: print(f'      {c:5d}  {p}')
