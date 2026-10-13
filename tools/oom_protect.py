#!/usr/bin/env python3
"""oom_protect: tell systemd-oomd to avoid Comparator checks that have already run for a long time.

Purpose: a check cannot resume, so one that has run for hours is expensive to lose, while a check that started a minute ago costs
nothing. systemd-oomd (systemd 249) picks a leaf cgroup to kill and honours two cgroup attributes: user.oomd_avoid (chosen only if
no other candidate) and user.oomd_omit (never chosen). An unprivileged user can set them on cgroups the user manager owns, but the
ManagedOOMPreference= unit property does not set them for user units here, so this sets the attribute directly. It finds each
running Comparator process under the user manager, takes its cgroup, and, once the process has run for --min-age seconds, sets the
attribute (mode avoid by default, omit with --mode omit). New and short checks stay ordinary candidates. Note the trade-off:
protecting the checks leaves other leaf cgroups (for example the terminal's, holding the build) as the likely victims.
Does not touch the kernel OOM killer (oom_score_adj can only be raised without root) and cannot protect against a manual kill.
Usage: oom_protect.py [--min-age 1800] [--mode avoid|omit] [--loop 60] [--dry-run]
"""
import os, sys, time, argparse, subprocess, datetime
ap = argparse.ArgumentParser(); ap.add_argument('--min-age', type=int, default=1800); ap.add_argument('--mode', choices=['avoid', 'omit'], default='avoid')
ap.add_argument('--loop', type=int, default=0, help='repeat every N seconds (0: once)'); ap.add_argument('--dry-run', action='store_true'); a = ap.parse_args()
uid = os.getuid(); ROOT = f'/sys/fs/cgroup/user.slice/user-{uid}.slice/user@{uid}.service'; attr = f'user.oomd_{a.mode}'
log = lambda m: print(f"{datetime.datetime.now().astimezone().isoformat(timespec='seconds')} {m}", flush=True)


def age(pid):
    try: return float(subprocess.run(['ps', '-o', 'etimes=', '-p', str(pid)], capture_output=True, text=True).stdout.strip())
    except ValueError: return None


def cgroup_of(pid):
    try: return ROOT + open(f'/proc/{pid}/cgroup').read().strip().split('::')[1].split('user@%d.service' % uid)[1]
    except Exception: return None


def has_attr(path, name):
    return subprocess.run(['getfattr', '-n', name, path], capture_output=True).returncode == 0


def scan():
    pids = subprocess.run(['pgrep', '-f', r'\.lake/build/bin/comparator ComparatorChallenges/'], capture_output=True, text=True).stdout.split()
    seen = {}
    for p in pids:
        if open(f'/proc/{p}/comm').read().strip() != 'comparator': continue
        cg = cgroup_of(p); t = age(p)
        if cg and t is not None and os.path.isdir(cg): seen[cg] = max(seen.get(cg, 0), t)
    for cg, t in sorted(seen.items(), key=lambda x: -x[1]):
        name = os.path.basename(cg)
        if t < a.min_age: log(f"{name}: running {t:.0f} s, below {a.min_age}; left as an ordinary candidate"); continue
        have = [m for m in ('avoid', 'omit') if has_attr(cg, f'user.oomd_{m}')]
        if have: log(f"{name}: running {t:.0f} s, already {have[0]}"); continue
        if a.dry_run: log(f"{name}: running {t:.0f} s, would set {attr}"); continue
        r = subprocess.run(['setfattr', '-n', attr, '-v', '1', cg], capture_output=True, text=True)
        log(f"{name}: running {t:.0f} s, set {attr}" if r.returncode == 0 else f"{name}: could not set {attr}: {r.stderr.strip()}")


while True:
    scan()
    if not a.loop: break
    time.sleep(a.loop)
