#!/usr/bin/env python3
"""export_probe: measure the size of a configuration's solution export without running the kernel check.

Purpose: a Comparator check streams a text export of the solution's declarations (lean4export) and then has the Lean kernel re-check
it. Check time follows the export size loosely (see REPORT.md 3d) but the size is only recorded for checks run after a monitor fix, and
only learned part-way into a check. This runs the export step alone for each configuration, with the same targets Comparator passes
(the Quot declarations, the theorem names, the permitted axioms, the primitives it always exports and any definition names), counts the
bytes and discards them (nothing is stored). While the stream passes it also tallies, by counting substrings of each batch of complete lines,
the records of each kind (expression nodes and their kinds, theorem/definition/inductive records, natural-number and string literals)
and the number of distinct applications of the kernel-computation lemma of_decide_eq_true (the proof term `decide +kernel` leaves
behind). The export is a DAG in which every distinct expression is written once, so these are counts of distinct nodes, not of uses in
the source, and a constant that is merely present appears once; the application count is the number of distinct propositions proved
this way. All of
it with wall time and peak memory in results/export-probe.csv, so the size of
every configuration, including those not yet checked, is known cheaply and early enough to schedule with. Resumable (configurations already
in the CSV are skipped). It only exports the solution module's stream (the larger one); the challenge's stream is a few hundred MB of
Mathlib declarations. It needs the closure to be built (every module has an .olean); unbuilt configurations are listed and skipped.
It runs lean4export outside Comparator's sandbox: it only imports the already-built modules, which `lake build` has already elaborated
unsandboxed. A job starts only if MemAvailable stays above --reserve-gib after reserving --est-gib (a large export used about 10 GiB).
Usage: export_probe.py [CONFIG ...] [--pending | --missing | --all] [--jobs 1] [--reserve-gib 12] [--est-gib 10] [--dry-run]
  --missing (default) configurations with no export size in results/cmp-all/configs.csv and none in the probe CSV; --pending only the
  unchecked ones; --all everything. Prints a validation line comparing probe sizes with sizes recorded by checks, where both exist.
"""
import os, re, sys, csv, json, time, argparse, subprocess, datetime
ap = argparse.ArgumentParser(); ap.add_argument('configs', nargs='*')
g = ap.add_mutually_exclusive_group(); g.add_argument('--pending', action='store_true'); g.add_argument('--missing', action='store_true'); g.add_argument('--all', action='store_true')
ap.add_argument('--jobs', type=int, default=1); ap.add_argument('--reserve-gib', type=float, default=12); ap.add_argument('--est-gib', type=float, default=10)
ap.add_argument('--dry-run', action='store_true'); a = ap.parse_args()
base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')); root = base + '/src/lean'; out = base + '/results/export-probe.csv'
# what Comparator always exports besides the theorem names (copied from the "Exporting #[...]" line of a check's output)
QUOT = ['Quot', 'Quot.mk', 'Quot.lift', 'Quot.ind']
PRIM = ['Nat.add', 'Nat.sub', 'Nat.mul', 'Nat.pow', 'Nat.gcd', 'Nat.div', 'Nat.mod', 'Nat.beq', 'Nat.ble', 'Nat.land', 'Nat.lor', 'Nat.xor', 'Nat.shiftLeft',
        'Nat.shiftRight', 'String.ofList', 'Char.ofNat', 'List', 'eagerReduce', 'Nat', 'String', 'String.mk', 'Char', 'optParam', 'autoParam', 'semiOutParam', 'outParam']
imp = re.compile(rb"^\s*(?:public\s+|meta\s+)*import\s+(?:public\s+|meta\s+)*(\S+)", re.M)
deps_cache = {}


def deps(m):
    if m not in deps_cache:
        try: deps_cache[m] = [x.decode() for x in imp.findall(open(os.path.join(root, *m.split('.')) + '.lean', 'rb').read()) if x.decode().startswith(('OAI', 'ComparatorChallenges'))]
        except OSError: deps_cache[m] = []
    return deps_cache[m]


def built(c):
    seen, todo = set(), [c['solution_module']]
    while todo:
        m = todo.pop()
        if m in seen: continue
        seen.add(m); todo += deps(m)
        if not os.path.exists(os.path.join(root, '.lake/build/lib/lean', *m.split('.')) + '.olean'): return False
    return True


def avail_gib():
    for l in open('/proc/meminfo'):
        if l.startswith('MemAvailable:'): return int(l.split()[1]) / 2**20


KINDS = {'expr_nodes': b'"ie":', 'app': b'{"app":{', 'lam': b'"lam":{', 'forallE': b'{"forallE":{', 'const_nodes': b'{"const":{', 'letE': b'"letE":{', 'proj': b'"proj":{',
         'thm': b'{"thm":{', 'def': b'{"def":{', 'inductive': b'{"inductive":{', 'opaque': b'{"opaque":{', 'axiom': b'{"axiom":{',
         'nat_lits': b'"natVal":', 'str_lits': b'"strVal":'}
DECIDE = re.compile(rb'\{"in":(\d+),"str":\{"pre":0,"str":"of_decide_eq_true"\}\}')
CONST = re.compile(rb'\{"const":\{"name":(\d+),"us":\[[^\]]*\]\},"ie":(\d+)\}')


def probe(name, c):
    targets = QUOT + c['theorem_names'] + c.get('permitted_axioms', []) + PRIM + (c.get('definition_names') or [])
    env = dict(os.environ, PATH=f"{base}/ext/lean4export/.lake/build/bin:{base}/ext/bin:{os.environ['HOME']}/.elan/bin:{os.environ['PATH']}", LEAN_ABORT_ON_PANIC='1')
    t0 = time.time(); started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
    p = subprocess.Popen(['lake', 'env', 'lean4export', c['solution_module'], '--'] + targets, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = 0; tally = dict.fromkeys(KINDS, 0); decide_id = None; decide_nodes = set(); decide_apps = 0; rest = b''
    while True:
        b = p.stdout.read(8 << 20)
        if not b: break
        n += len(b); b = rest + b; cut = b.rfind(b'\n') + 1; rest, b = b[cut:], b[:cut]          # count over whole lines only
        for k, pat in KINDS.items(): tally[k] += b.count(pat)
        if decide_id is None:
            m = DECIDE.search(b)
            if m: decide_id = m.group(1)
        if decide_id is not None:
            for m in CONST.finditer(b):                                                      # the constant's expression node(s)
                if m.group(1) == decide_id: decide_nodes.add(m.group(2))
            for nd in decide_nodes: decide_apps += b.count(b'"fn":' + nd + b'}')              # distinct applications whose function is that node
    _, status, ru = os.wait4(p.pid, 0)
    rc = os.waitstatus_to_exitcode(status)
    return dict(config=name, solution_module=c['solution_module'], exit=rc, export_bytes=n, seconds=round(time.time() - t0, 1),
                max_rss_gib=round(ru.ru_maxrss / 2**20, 2), started=started, of_decide_eq_true_apps=decide_apps, **tally)


cfgs = {f[:-5]: json.load(open(f'{root}/ComparatorChallenges/{f}')) for f in sorted(os.listdir(root + '/ComparatorChallenges')) if f.endswith('.json')}
have = {r['config'] for r in csv.DictReader(open(out))} if os.path.exists(out) else set()
rec = {r['config']: r for r in csv.DictReader(open(base + '/results/cmp-all/configs.csv'))}
if a.configs: todo = [n for n in a.configs if n not in have]
elif a.all: todo = [n for n in cfgs if n not in have]
elif a.pending: todo = [n for n in cfgs if rec.get(n, {}).get('status') != 'accepted' and n not in have]
else: todo = [n for n in cfgs if not rec.get(n, {}).get('export_mb_total') and n not in have]
ready = [n for n in todo if built(cfgs[n])]
print(f"{len(todo)} to probe; {len(ready)} have a built closure; {len(todo) - len(ready)} skipped as unbuilt")
if a.dry_run: print(' '.join(ready)); sys.exit(0)
cols = ['config', 'solution_module', 'exit', 'export_bytes', 'seconds', 'max_rss_gib', 'started', 'of_decide_eq_true_apps', *KINDS]
import concurrent.futures as cf


def record(r):
    new = not os.path.exists(out)
    with open(out, 'a', newline='') as fh:
        w = csv.DictWriter(fh, cols)
        if new: w.writeheader()
        w.writerow(r)
    print(r['config'], r['exit'], f"{r['export_bytes'] / 1e6:.0f} MB", f"{r['seconds']} s", f"{r['max_rss_gib']} GiB", flush=True)


with cf.ThreadPoolExecutor(a.jobs) as pool:
    futs = set()
    for n in ready:
        while len(futs) >= a.jobs or avail_gib() - a.est_gib < a.reserve_gib:       # wait for a free slot and for memory
            for f in [f for f in futs if f.done()]: futs.discard(f); record(f.result())
            time.sleep(1)
        futs.add(pool.submit(probe, n, cfgs[n]))
    for f in cf.as_completed(futs): record(f.result())
pr = {r['config']: r for r in csv.DictReader(open(out))} if os.path.exists(out) else {}
both = [(n, int(pr[n]['export_bytes']) / 1e6, float(rec[n]['export_mb_largest'])) for n in pr if rec.get(n, {}).get('export_mb_largest')]
if both: print('validation against sizes recorded by checks (probe MB / recorded largest-stream MB):', ', '.join(f"{n} {p:.0f}/{r:.0f}" for n, p, r in both))
