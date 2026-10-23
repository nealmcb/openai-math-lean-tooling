#!/usr/bin/env python3
"""nanoda_isolate_run: run one or more nanoda builds on already exported declarations and record the outcome of each run.

Purpose: nanoda_lib issues 55 and 57: compare nanoda builds (for example upstream master before and after a pull request) on the small exports in scratch/isolate (single
declarations that overflowed the checker stack, made by tools/isolate_decl.py) without exporting anything again. Each run writes a nanoda config next to the export (in OUTDIR),
runs the build in a transient systemd scope with a memory cap and no swap and a wall-clock timeout, and appends one JSON line to results/nanoda-isolate.jsonl: nanoda build, commit of
its source tree, export, threads, exit code, wall and CPU seconds, peak RSS and the last output line.
Usage: nanoda_isolate_run.py --nanoda PATH [--nanoda PATH ...] [--threads 1] [--mem 30G] [--timeout 900] EXPORT [EXPORT ...]
"""
import os, sys, json, time, subprocess, datetime, tempfile
base = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
args = sys.argv[1:]; nanodas, exports, i, opt = [], [], 0, {'--threads': '1', '--mem': '30G', '--timeout': '900'}
while i < len(args):
    if args[i] == '--nanoda': nanodas.append(os.path.abspath(args[i + 1])); i += 2
    elif args[i] in opt: opt[args[i]] = args[i + 1]; i += 2
    else: exports.append(os.path.abspath(args[i])); i += 1
out = os.path.join(base, 'results/nanoda-isolate.jsonl'); tmp = tempfile.mkdtemp(prefix='nanoda-isolate-')
def commit(binpath):
    d = binpath
    for _ in range(4):
        d = os.path.dirname(d)
        if os.path.exists(os.path.join(d, 'Cargo.toml')):
            return subprocess.run(['git', '-C', d, 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip() or None
    return None
for exp in exports:
    cfg = os.path.join(tmp, os.path.basename(exp) + '.json')
    json.dump({'use_stdin': False, 'export_file_path': exp, 'permitted_axioms': ['propext', 'Quot.sound', 'Classical.choice'], 'unpermitted_axiom_hard_error': True,
               'num_threads': int(opt['--threads']), 'nat_extension': True, 'string_extension': True}, open(cfg, 'w'))
    for nd in nanodas:
        t0 = time.time()
        p = subprocess.run(['systemd-run', '--user', '--scope', '--quiet', '-p', f"MemoryMax={opt['--mem']}", '-p', 'MemorySwapMax=0', '/usr/bin/time', '-f', '%e %U %S %M',
                            'timeout', '-s', 'KILL', opt['--timeout'], nd, cfg], capture_output=True, text=True)
        err = p.stderr.strip().splitlines(); last = err[-1] if err else ''
        wall, user, sys_, rss = (last.split() + [None] * 4)[:4] if last.replace('.', '').replace(' ', '').isdigit() else (None,) * 4
        rec = dict(when=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), nanoda=nd, commit=commit(nd), export=os.path.basename(exp), threads=int(opt['--threads']),
                   rc=p.returncode, wall_s=float(wall) if wall else round(time.time() - t0, 1), cpu_s=round(float(user) + float(sys_), 1) if user else None, rss_gib=round(int(rss) / 1048576, 2) if rss else None,
                   tail=(p.stdout.strip().splitlines() or err[:-1] or [''])[-1][:200])
        open(out, 'a').write(json.dumps(rec) + '\n'); print(json.dumps({k: rec[k] for k in ('commit', 'export', 'rc', 'wall_s', 'rss_gib', 'tail')}), flush=True)
