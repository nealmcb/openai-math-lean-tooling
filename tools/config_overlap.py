#!/usr/bin/env python3
"""config_overlap: how much do the import closures of the Comparator configs (and of pipeline batches) overlap?

Purpose: generated C is per module, so shared modules mean the same C is built once but needed by many configs, and is
archived and restored again whenever a later batch needs it. This measures that overlap: per-config closure sizes vs
their union, how many configs each module serves, and the same across the batches recorded in results/cmp-all/batches.jsonl
(with the number of files restored per batch, from driver.log). Usage: config_overlap.py   (reads src/lean)
"""
import os, re, json, glob, collections, statistics as st
base = '/home/srv/s/math/openai-math'; root = base + '/src/lean'
imp = re.compile(rb"^\s*(?:public\s+|meta\s+)*import\s+(?:public\s+|meta\s+)*(\S+)", re.M)
cache = {}
def deps(m):
    if m not in cache:
        p = os.path.join(root, *m.split('.')) + '.lean'
        cache[m] = [x.decode() for x in imp.findall(open(p, 'rb').read()) if os.path.exists(os.path.join(root, *x.decode().split('.')) + '.lean')] if os.path.exists(p) else []
    return cache[m]
def closure(roots):
    seen, todo = set(), list(roots)
    while todo:
        m = todo.pop()
        if m in seen: continue
        seen.add(m); todo += deps(m)
    return seen
cfgs = {}
for c in sorted(glob.glob(root + '/ComparatorChallenges/*.json')):
    d = json.load(open(c)); cfgs[os.path.basename(c)[:-5]] = closure([d['solution_module'], d['challenge_module']])
U = set().union(*cfgs.values()); S = sum(len(v) for v in cfgs.values())
print(f"{len(cfgs)} configs: sum of closure sizes {S:,}; union {len(U):,}; each module serves {S/len(U):.2f} configs on average")
mult = collections.Counter(m for v in cfgs.values() for m in v)
b = collections.Counter('1' if c == 1 else '2-5' if c <= 5 else '6-20' if c <= 20 else '21-100' if c <= 100 else '>100' for c in mult.values())
print("modules by number of configs that need them:", {k: b[k] for k in ('1', '2-5', '6-20', '21-100', '>100')})
print(f"  needed by exactly one config: {100*b['1']/len(U):.0f}% of modules; by more than 20: {100*(b['21-100']+b['>100'])/len(U):.1f}%")
top = mult.most_common(3); print("most shared modules:", [(m, c) for m, c in top])
sm = sorted(len(v) for v in cfgs.values()); small = [v for v in cfgs.values() if len(v) < 100]
inbig = set().union(*[v for v in cfgs.values() if len(v) >= 1000]) if any(len(v) >= 1000 for v in cfgs.values()) else set()
print(f"configs under 100 modules: {len(small)}; share of their modules that also sit in some 1000+ module config: "
      f"{100*sum(len(v & inbig) for v in small)/max(1,sum(len(v) for v in small)):.0f}%")
# batches
bs = [json.loads(l) for l in open(base + '/results/cmp-all/batches.jsonl')]
per = [closure([m for n in x['configs'] for m in (json.load(open(f'{root}/ComparatorChallenges/{n}.json'))['solution_module'], json.load(open(f'{root}/ComparatorChallenges/{n}.json'))['challenge_module'])]) for x in bs]
BU = set().union(*per); BS = sum(len(p) for p in per)
bm = collections.Counter(m for p in per for m in p)
print(f"\n{len(bs)} batches so far: sum of batch closures {BS:,}; union {len(BU):,}; modules needed by more than one batch: {sum(1 for c in bm.values() if c > 1):,} ({100*sum(1 for c in bm.values() if c > 1)/len(BU):.0f}%)")
rest = [int(m.group(1)) for l in open(base + '/results/cmp-all/driver.log') for m in [re.search(r'restored=(\d+)', l)] if m]
print(f"files restored from archives at batch starts: {sum(rest):,} in total ({sum(rest)/3:,.0f} modules' C worth), median {st.median(rest):.0f} per batch; "
      f"the union of all batch modules is {len(BU):,}, so each module's C was restored {sum(rest)/3/len(BU):.2f} times on average")
