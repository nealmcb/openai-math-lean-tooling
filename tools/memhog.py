#!/usr/bin/env python3
"""memhog: allocate and keep touching anonymous memory to create controlled memory pressure (for the oomd lab).

Purpose: recreate the 2026-10-11 conditions (swap filling, reclaim thrash) on purpose, in a cgroup of your choosing, to see which
cgroup systemd-oomd kills. Run it ONLY inside a transient scope/service so the blast radius is known:
   systemd-run --user --scope --unit=memhog python3 tools/memhog.py --gib 60 --rate 500
Allocates --gib in 64 MiB chunks at --rate MiB/s, then (unless --no-thrash) keeps rewriting random pages so reclaim never settles.
Prints progress every 5 s. Exits on SIGTERM/SIGINT (or when --max-seconds passes). A memhog that is killed by oomd just disappears.
"""
import sys, time, os, random, argparse, signal
ap = argparse.ArgumentParser(); ap.add_argument('--gib', type=float, default=8); ap.add_argument('--rate', type=float, default=500, help='MiB/s')
ap.add_argument('--no-thrash', action='store_true'); ap.add_argument('--max-seconds', type=float, default=900); a = ap.parse_args()
stop = [False]; signal.signal(signal.SIGTERM, lambda *x: stop.__setitem__(0, True)); signal.signal(signal.SIGINT, lambda *x: stop.__setitem__(0, True))
CH = 64 * 2**20; chunks = []; t0 = time.time(); last = 0
print(f'memhog pid {os.getpid()} cgroup {open("/proc/self/cgroup").read().strip()} target {a.gib} GiB', flush=True)
while not stop[0] and time.time() - t0 < a.max_seconds:
    if len(chunks) * CH < a.gib * 2**30:
        b = bytearray(CH)
        for i in range(0, CH, 4096): b[i] = 1                       # touch every page so it is really resident
        chunks.append(b); time.sleep(CH / (a.rate * 2**20))
    elif not a.no_thrash:
        c = chunks[random.randrange(len(chunks))]
        for _ in range(2000): c[random.randrange(CH)] = 2            # random writes keep pages hot, forcing swap in/out
    else: time.sleep(0.5)
    if time.time() - last > 5:
        last = time.time(); print(f'{time.time() - t0:5.0f}s held {len(chunks) * CH / 2**30:5.1f} GiB', flush=True)
print('memhog exiting', flush=True)
