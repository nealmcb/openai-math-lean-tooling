#!/usr/bin/env python3
"""priority_build: build the modules of many Comparator configurations in priority order, several `lake build` processes at once, without
ever letting two of them compile the same module.

Purpose: the run cannot end before the config with the longest check has been built, started and finished, and Lake cannot prioritise inside
one build (it starts every ready job at once). This does the prioritising outside: it computes each configuration's import closure from the
source text, including the modules of the other Lake packages (carleson, TauCeti, ... but not Mathlib and its cached dependencies), takes the
configurations in the order you give (longest predicted check first), and launches `lake build CHALLENGE SOLUTION` for the next one whose set of
still-unbuilt modules does not overlap the unbuilt modules of any build already running; a blocked configuration is skipped for now and
retried as the running builds finish their shared modules, so a later, smaller configuration may start before a blocked, larger one. A module
counts as built when both its .olean and .trace exist (Lake writes the trace last). At most --max-builds run at once; the number of
concurrent compiles is capped globally by the throttled sysroot (tools/make_throttled_sysroot.sh) through LEAN_SLOTS, and builds are pinned to
--build-cpus with taskset, so compiles do not take CPUs from the checks. Each build's output goes to RESULTS/builds/CONFIG.log with its exit
code in RESULTS/builds.jsonl. Used by tools/cloud_run.py; runnable alone for a dry run on any checkout:
  priority_build.py --order results/check-cost-predictions.csv --dry-run     (prints the plan: unbuilt modules per configuration)
Usage as a library: pb = PriorityBuilder(base, configs, ...); while not pb.step(): time.sleep(2)
"""
import os, re, sys, json, time, subprocess, datetime

CACHED = {'mathlib', 'batteries', 'aesop', 'Qq', 'plausible', 'proofwidgets', 'importGraph', 'LeanSearchClient', 'Cli', 'doc-gen4', 'MD4Lean', 'BibtexQuery',
          'checkdecls', 'leansqlite'}          # packages whose .olean files come from the Mathlib cache (never compiled here)
imp = re.compile(rb"^\s*(?:public\s+|meta\s+)*import\s+(?:public\s+|meta\s+)*(\S+)", re.M)


class Resolver:
    """Maps a module name to its source file and build directory, for the project and its non-cached packages."""

    def __init__(self, root):
        self.roots = {}                                 # top-level component -> (source dir, build lib dir)
        pk = os.path.join(root, '.lake/packages')
        for p in sorted(os.listdir(pk)) if os.path.isdir(pk) else []:
            if p in CACHED: continue
            d = os.path.join(pk, p)
            for e in os.listdir(d):
                if e.startswith('.'): continue
                top = e[:-5] if e.endswith('.lean') else e if os.path.isdir(os.path.join(d, e)) else None
                if top and top not in ('lakefile', 'lake-manifest', 'README', 'docs', 'scripts', 'test', 'tests', 'Test', 'Tests', 'lean-toolchain'):
                    self.roots.setdefault(top, (d, os.path.join(d, '.lake/build/lib/lean')))
        for top in ('OAI', 'ComparatorChallenges'):
            self.roots[top] = (root, os.path.join(root, '.lake/build/lib/lean'))
        self.cache = {}

    def src(self, m):
        r = self.roots.get(m.split('.')[0])
        return os.path.join(r[0], *m.split('.')) + '.lean' if r else None

    def stem(self, m):
        r = self.roots.get(m.split('.')[0])
        return os.path.join(r[1], *m.split('.')) if r else None

    def imports(self, m):
        if m not in self.cache:
            p = self.src(m); out = []
            if p and os.path.exists(p):
                out = [x.decode() for x in imp.findall(open(p, 'rb').read()) if x.decode().split('.')[0] in self.roots]
            self.cache[m] = out
        return self.cache[m]

    def closure(self, roots):
        seen, todo = set(), list(roots)
        while todo:
            m = todo.pop()
            if m in seen or self.src(m) is None or not os.path.exists(self.src(m)): continue
            seen.add(m); todo += self.imports(m)
        return seen

    def built(self, m):
        s = self.stem(m)
        return bool(s) and os.path.exists(s + '.olean') and os.path.exists(s + '.trace')


class PriorityBuilder:
    def __init__(self, base, configs, max_builds=6, lean_slots=24, build_cpus=None, results=None, log=print):
        self.base = base; self.root = base + '/src/lean'; self.R = results or base + '/results/cmp-all'; self.log = log
        os.makedirs(self.R + '/builds', exist_ok=True)
        self.res = Resolver(self.root); self.max_builds = max_builds; self.lean_slots = lean_slots; self.cpus = build_cpus
        self.pending = list(configs); self.running = {}       # config -> (Popen, unbuilt set at launch, start time)
        self.done = {}; self.t0 = time.time()
        self.targets = {}
        for c in configs:
            d = json.load(open(f'{self.root}/ComparatorChallenges/{c}.json')); self.targets[c] = [d['challenge_module'], d['solution_module']]
        t = time.time(); self.clo = {c: self.res.closure(self.targets[c]) for c in configs}
        self.log(f"closures of {len(configs)} configurations computed in {time.time() - t:.0f} s; union {len(set().union(*self.clo.values()))} modules")

    def unbuilt(self, c): return {m for m in self.clo[c] if not self.res.built(m)}

    def inflight(self):
        s = set()
        for p, u, _ in self.running.values(): s |= {m for m in u if not self.res.built(m)}
        return s

    def launch(self, c, u):
        env = dict(os.environ, LEAN_SYSROOT=self.base + '/ext/sysroot-throttled', LEAN_SLOTS=str(self.lean_slots))
        cmd = (['taskset', '-c', self.cpus] if self.cpus else []) + [self.base + '/ext/sysroot-throttled/bin/lake', 'build', *self.targets[c]]
        p = subprocess.Popen(cmd, cwd=self.root, env=env, stdout=open(f'{self.R}/builds/{c}.log', 'w'), stderr=subprocess.STDOUT)
        self.running[c] = (p, u, time.time()); self.log(f"build {c}: {len(u)} modules to compile; {len(self.running)} running, {len(self.pending) - 1} waiting")

    def step(self):
        """One scheduling pass. Returns True when every configuration has been built (or failed)."""
        for c, (p, u, t) in list(self.running.items()):
            if p.poll() is not None:
                del self.running[c]; self.done[c] = p.returncode
                open(self.R + '/builds.jsonl', 'a').write(json.dumps(dict(config=c, exit=p.returncode, seconds=round(time.time() - t), modules=len(u),
                    t=datetime.datetime.now().astimezone().isoformat(timespec='seconds'))) + '\n')
                self.log(f"build {c} ended: exit {p.returncode} after {time.time() - t:.0f} s")
        if len(self.running) < self.max_builds:
            busy = self.inflight()
            for c in list(self.pending):
                if len(self.running) >= self.max_builds: break
                u = self.unbuilt(c)
                if not u:
                    self.pending.remove(c); self.done[c] = 0; continue
                if u & busy: continue
                self.pending.remove(c); self.launch(c, u); busy |= u
        return not self.pending and not self.running


if __name__ == '__main__':
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')); import csv
    order = sys.argv[sys.argv.index('--order') + 1] if '--order' in sys.argv else base + '/results/check-cost-predictions.csv'
    names = [r['config'] for r in sorted(csv.DictReader(open(order)), key=lambda r: -float(r['pred_s']))]
    names = [n for n in names if os.path.exists(f'{base}/src/lean/ComparatorChallenges/{n}.json')]
    pb = PriorityBuilder(base, names)
    if '--dry-run' in sys.argv:
        tot = 0
        for n in names[:15]: u = pb.unbuilt(n); print(f"{n:28s} closure {len(pb.clo[n]):6d} unbuilt {len(u):6d}")
        print('configurations with something to build:', sum(1 for n in names if pb.unbuilt(n)), 'of', len(names)); sys.exit(0)
    while not pb.step(): time.sleep(2)
