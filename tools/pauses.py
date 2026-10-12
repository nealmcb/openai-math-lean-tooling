#!/usr/bin/env python3
"""pauses: pause intervals of the run (from tools/pause.sh and resume.sh entries in driver.log) and overlap arithmetic.

Purpose: wall-clock times of checks and builds include the time the whole run was frozen by SIGSTOP (manual pause,
screen-blank resume pairs). The raw records are left as measured; this computes how much of any interval was paused
so reports can use active time. A pause freezes every process of the run, so any check or build in flight during a pause
loses exactly the overlap. Intervals come from the lines "<iso time> PAUSED n processes" and "<iso time> RESUMED"
in results/cmp-all/driver.log. Importable (load_pauses, overlap_s, batch_build_intervals); run as a script to list them.
"""
import re, datetime as dt
LOG = '/home/srv/s/math/openai-math/results/cmp-all/driver.log'


def load_pauses(path=LOG):
    out, start = [], None
    for l in open(path):
        m = re.match(r'(\S+) (PAUSED|RESUMED)', l)
        if not m: continue
        t = dt.datetime.fromisoformat(m.group(1))
        if m.group(2) == 'PAUSED' and start is None: start = t
        elif m.group(2) == 'RESUMED' and start is not None: out.append((start, t)); start = None
    if start is not None: out.append((start, dt.datetime.now(start.tzinfo)))     # still paused
    return out


def overlap_s(a, b, pauses):
    """Seconds of [a, b] covered by pause intervals (datetimes must be timezone-aware)."""
    return sum(max(0.0, (min(b, e) - max(a, s)).total_seconds()) for s, e in pauses)


def batch_builds(path=LOG):
    """Ordered list of {id, start, end, wall} for every 'batch X: build exit=... Ns' line in driver.log (ids can repeat across restarts)."""
    out = []
    for l in open(path):
        m = re.match(r'(\S+) pipeline: batch (\S+?): build exit=\S+ ([\d.]+)s', l)
        if m:
            end = dt.datetime.fromisoformat(m.group(1)); w = float(m.group(3))
            out.append(dict(id=m.group(2), start=end - dt.timedelta(seconds=w), end=end, wall=w))
    return out


def batch_build_intervals(path=LOG):
    """batch id -> (start, end) of its build step, from 'batch N: build exit=0 123.4s' lines (timestamp = end)."""
    out = {}
    for l in open(path):
        m = re.match(r'(\S+) pipeline: batch (\d+): build exit=\S+ ([\d.]+)s', l)
        if m:
            end = dt.datetime.fromisoformat(m.group(1)); out[m.group(2)] = (end - dt.timedelta(seconds=float(m.group(3))), end)
    return out


if __name__ == '__main__':
    for s, e in load_pauses(): print(f"{s.isoformat(timespec='seconds')} -> {e.isoformat(timespec='seconds')}  {(e - s).total_seconds():.0f} s")
