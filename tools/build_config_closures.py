#!/usr/bin/env python3
"""build_config_closures: `lake build` the challenge and solution modules of Comparator configurations, without checking them.

Purpose: tools/nanoda_ab.py needs every solution's closure built under src/lean before it exports and runs nanoda. On the laptop this takes
unchanged modules from the published OAI Lake cache (through tools/with_oai_cache.sh) and compiles only the rest, one configuration at a time
in a systemd scope capped at MEMMAX. Prints one line per configuration: name, lake exit code, seconds, modules compiled.
Usage: [MEMMAX=20G] build_config_closures.py CONFIG_NAME...   (as in ComparatorChallenges/<name>.json without .json; the checkout is the one
       next to tools/, or $CHECKOUT)
"""
import json, os, subprocess, sys, time

here = os.path.dirname(os.path.abspath(__file__))
base = os.environ.get('CHECKOUT', os.path.dirname(here))
lean = os.path.join(base, 'src/lean')
for name in sys.argv[1:]:
    cfg = json.load(open(os.path.join(lean, 'ComparatorChallenges', name + '.json')))
    t = time.time()
    p = subprocess.run(['systemd-run', '--user', '--scope', '-q', '-p', 'MemoryMax=' + os.environ.get('MEMMAX', '20G'),
                        os.path.join(here, 'with_oai_cache.sh'), 'lake', 'build', cfg['challenge_module'], cfg['solution_module']],
                       capture_output=True, text=True, env=dict(os.environ, CHECKOUT=base))
    built = sum(l.lstrip().startswith(('✔', 'Built')) and 'Built' in l for l in p.stdout.splitlines())
    print(f'{name}\t{p.returncode}\t{time.time() - t:.0f}\t{built}', flush=True)
    if p.returncode: print(p.stdout[-2000:], p.stderr[-2000:], sep='\n', file=sys.stderr)
