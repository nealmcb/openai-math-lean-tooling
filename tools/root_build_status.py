#!/usr/bin/env python3
"""root_build_status: how many of the modules that `import OAI` pulls in already have a built .olean?

Purpose: the root-import measurement (peak mappings of a process that imports the aggregate OAI.lean, predicted well above the default
vm.max_map_count of 65,530) needs every module of that import closure built, or the import fails for a different reason (a missing
file) than the mapping limit. This lists the closure from results/oai-closure-sizes.jsonl (91,762 modules reachable from OAI.lean,
from tools/importclosure.py) and counts those with an .olean under src/lean/.lake/build/lib/lean, plus the unbuilt ones' share of
the source bytes. Also splits the unbuilt ones into those the Comparator run will still build (results/comparator-solution-closure.txt) and those in no
config's closure. With --estimate it also predicts the compile time of the never-built ones from results/module-times.csv.gz: seconds per
KB of source measured on built modules of the same top-level area, times each module's source size (module-seconds under load, an
upper bound on isolated cost; heavy generated modules make the true figure uncertain). Usage: root_build_status.py [--list] [--estimate]
"""
import json, os, sys
base = '/home/srv/s/math/openai-math'; lib = base + '/src/lean/.lake/build/lib/lean'; src = base + '/src/lean'
mods = [json.loads(l)['module'] for l in open(base + '/results/oai-closure-sizes.jsonl')]
miss = [m for m in mods if not os.path.exists(os.path.join(lib, *m.split('.')) + '.olean')]
size = lambda m: os.path.getsize(os.path.join(src, *m.split('.')) + '.lean') if os.path.exists(os.path.join(src, *m.split('.')) + '.lean') else 0
print(f"{len(mods)} modules reachable from OAI.lean; {len(mods) - len(miss)} built, {len(miss)} not built ({100 * len(miss) / len(mods):.1f}%)")
if miss:
    tot = sum(size(m) for m in mods); mb = sum(size(m) for m in miss)
    print(f"unbuilt source: {mb / 1e6:.0f} MB of {tot / 1e6:.0f} MB ({100 * mb / tot:.1f}%)")
    areas = {}
    for m in miss:
        k = m.split('.')[1] if '.' in m else m
        areas[k] = areas.get(k, 0) + 1
    print('unbuilt by top-level area:', sorted(areas.items(), key=lambda x: -x[1])[:8])
cl = base + '/results/comparator-solution-closure.txt'
if os.path.exists(cl):
    plan = {l.strip() for l in open(cl) if l.strip()}
    never = [m for m in miss if m not in plan]
    print(f"of the {len(miss)} unbuilt, {len(miss) - len(never)} are in the Comparator configs' closures (the run will build them) and {len(never)} are in no config's closure")
if '--estimate' in sys.argv:
    import csv, gzip, collections
    rows = [r for r in csv.DictReader(gzip.open(base + '/results/module-times.csv.gz', 'rt')) if r['likely_pause_artifact'] != '1']
    area = collections.defaultdict(lambda: [0.0, 0])
    for r in rows:
        a = r['module'].split('.')[1] if '.' in r['module'] else r['module']
        area[a][0] += float(r['first_build_s']); area[a][1] += int(r['source_bytes'] or 0)
    glob = sum(v[0] for v in area.values()) / sum(v[1] for v in area.values())
    rate = lambda m: area[m.split('.')[1]][0] / area[m.split('.')[1]][1] if '.' in m and area[m.split('.')[1]][1] else glob
    est = sum(rate(m) * size(m) for m in never)
    cert = [m for m in never if 'Certificate' in m]
    print(f"never-built: {len(never)} modules, {sum(size(m) for m in never) / 1e6:.0f} MB source; {len(cert)} have 'Certificate' in the name ({sum(size(m) for m in cert) / 1e6:.0f} MB)")
    print(f"estimated compile time: {est / 3600:.1f} module-hours (all built modules: {sum(v[0] for v in area.values()) / 3600:.0f} module-hours for {sum(v[1] for v in area.values()) / 1e6:.0f} MB)")
if '--list' in sys.argv: print('\n'.join(miss))
