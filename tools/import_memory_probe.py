#!/usr/bin/env python3
"""import_memory_probe: how much memory does importing N OAI modules (plus Mathlib) take, split by kind?

Purpose: predict the memory needed to compile the aggregate OAI.lean (which imports ~91.8k in-repo modules) from direct
measurements at several import-set sizes, instead of extrapolating one early test. For each size it imports a random
sample of already-built OAI modules (plus everything they import), waits until the process settles, then records from
/proc: RssAnon (private heap, must fit in RAM/swap), RssFile (mapped .olean pages: shared, evictable page cache),
the number of mapped .olean files and their total bytes. Run under tools/with_maxmap.sh with a raised vm.max_map_count:
  tools/with_maxmap.sh 262144 python3 tools/import_memory_probe.py SOURCE_IMPORT_FILE OUT.json [sizes...]
SOURCE_IMPORT_FILE: a Lean file of `import X` lines (for example scratch/ImportBuiltOAI.lean). Sizes default 0 1000 3000 6000 all.
"""
import sys, os, re, json, random, time, subprocess, signal
src, out = sys.argv[1], sys.argv[2]
base = '/home/srv/s/math/openai-math'; lean_root = base + '/src/lean'
imports = [l.strip() for l in open(src) if l.startswith('import OAI')]
sizes = [int(x) for x in sys.argv[3:]] or [0, 1000, 3000, 6000, len(imports)]
random.seed(7); order = random.sample(imports, len(imports))
res = []


def status(pid):
    d = {}
    for l in open(f'/proc/{pid}/status'):
        if l.startswith(('VmRSS', 'RssAnon', 'RssFile', 'RssShmem')):
            k, v = l.split(':'); d[k] = int(v.split()[0]) / 2**20          # GiB
    return d


for n in sizes:
    f = f'{base}/scratch/probe_{n}.lean'
    open(f, 'w').write('import Mathlib\n' + '\n'.join(order[:n]) + '\n#eval IO.sleep 60000\n')
    p = subprocess.Popen(['lake', 'env', 'lean', f], cwd=lean_root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    time.sleep(3); t0 = time.time(); pid = None; last = None; stable = 0
    while time.time() - t0 < 180:
        kids = subprocess.run(['pgrep', '-P', str(p.pid), '-x', 'lean'], capture_output=True, text=True).stdout.split()
        if kids:
            pid = int(kids[0])
            try: s = status(pid)
            except FileNotFoundError: break
            cur = s.get('VmRSS', 0)
            stable = stable + 1 if last and abs(cur - last) < 0.02 * max(cur, 1) else 0
            last = cur
            if stable >= 4 and cur > 1: break
        time.sleep(1.5)
    s = status(pid); maps = open(f'/proc/{pid}/maps').read().split('\n')
    files = {l.split(None, 5)[5] for l in maps if len(l.split(None, 5)) == 6 and l.split(None, 5)[5].endswith('.olean')}
    oai = [x for x in files if '/OAI/' in x]
    res.append(dict(requested_imports=n, mapped_olean_files=len(files), mapped_oai_oleans=len(oai),
                    mapped_oai_olean_bytes=sum(os.path.getsize(x) for x in oai), vmas=len([m for m in maps if m]),
                    seconds_to_settle=round(time.time() - t0), **{k: round(v, 2) for k, v in s.items()}))
    print(json.dumps(res[-1]), flush=True)
    os.killpg(p.pid, signal.SIGKILL); p.wait(); os.remove(f)
json.dump(res, open(out, 'w'), indent=1)
