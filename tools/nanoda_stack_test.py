#!/usr/bin/env python3
"""nanoda_stack_test: does a bigger checker stack get nanoda past a stack overflow, which declaration overflows, and what do the big runs cost?

Purpose: with the pinned nanoda each checker thread has a 16 MiB stack; DirectedFeedback and UniqueGamesTheorem die with "thread has overflowed its stack" (exit 134)
and UniqueGamesTheorem still dies at 1 GiB. The timing build of nanoda (tools/patches/nanoda-stack-and-decl-times.patch) reads the stack size in MiB from NANODA_STACK_MB
and writes a line when each declaration begins and ends, so after a crash the declarations that began and did not end name where it died. For each export given as
CONFIG=PATH this runs nanoda at the chosen thread count with the stacks in --stacks in turn, stopping at the first that succeeds (--no-escalate: run all), and records wall
seconds, CPU seconds, peak memory, the exit code, the last stderr lines and the in-flight declarations, in results/nanoda-stack-test.jsonl. No timeout, no memory cap.
Usage: nanoda_stack_test.py CONFIG=EXPORT [CONFIG=EXPORT ...] [--threads 64] [--stacks 1024,16384,65536] [--no-escalate] [--nanoda PATH] [--out DIR]
"""
import os, sys, json, time, subprocess
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
threads = int(arg('--threads', '64')); stacks = [int(x) for x in arg('--stacks', '1024,16384,65536').split(',')]
nanoda = arg('--nanoda', 'nanoda_bin'); out = arg('--out', 'results/nanoda-stack-test'); os.makedirs(out, exist_ok=True)
for spec in [a for a in sys.argv[1:] if '=' in a and not a.startswith('--')]:
    name, exp = spec.split('=', 1)
    for mb in stacks:
        tag = f'{name}.t{threads}.s{mb}'; cfg = f'{out}/{tag}.json'; times = f'{out}/{tag}.times'
        json.dump(dict(use_stdin=False, export_file_path=exp, permitted_axioms=['propext', 'Quot.sound', 'Classical.choice'], unpermitted_axiom_hard_error=True,
                       num_threads=threads, nat_extension=True, string_extension=True), open(cfg, 'w'))
        t = time.time(); err = open(f'{out}/{tag}.err', 'wb')
        p = subprocess.Popen([nanoda, cfg], env=dict(os.environ, NANODA_STACK_MB=str(mb), NANODA_DECL_TIMES=times), stdout=subprocess.DEVNULL, stderr=err)
        _, status, ru = os.wait4(p.pid, 0); wall = time.time() - t; rc = os.waitstatus_to_exitcode(status)
        inflight = []
        if os.path.exists(times):
            began, ended = {}, set()
            for l in open(times, errors='replace'):
                f = l.rstrip('\n').split('\t', 4)
                if f[0] == 'B' and len(f) == 5: began[f[1]] = f[4]
                elif f[0] == 'E' and len(f) == 5: ended.add(f[1])
            inflight = [n for i, n in began.items() if i not in ended][:8]
        tail = open(f'{out}/{tag}.err', errors='replace').read().strip().splitlines()[-4:]
        rec = dict(config=name, threads=threads, stack_mib=mb, exit=rc, wall_s=round(wall, 1), cpu_s=round(ru.ru_utime + ru.ru_stime, 1), rss_gib=round(ru.ru_maxrss / 2**20, 2),
                   in_flight_declarations=inflight, stderr_tail=tail, export_bytes=os.path.getsize(exp))
        open('results/nanoda-stack-test.jsonl', 'a').write(json.dumps(rec) + '\n'); print(json.dumps(rec), flush=True)
        if rc == 0 and '--no-escalate' not in sys.argv: break
