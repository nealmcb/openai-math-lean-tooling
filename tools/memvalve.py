#!/usr/bin/env python3
"""memvalve: freeze a build's process tree while the machine is short of memory, thaw it when pressure subsides.

Purpose: systemd-oomd kills a whole cgroup when the user session's memory pressure stays above 50% for 20 s. A Lake build of heavy
modules can push the machine there. MemoryValve(root_pid).step(), called every second or two while the build runs, sends SIGSTOP to the
whole tree when memory pressure (PSI "some" avg10, %) exceeds psi_pause or MemAvailable drops under min_avail_gib, and SIGCONT after
three consecutive calm samples (pressure under psi_resume and MemAvailable over resume_avail_gib). Frozen processes keep their memory
but stop allocating and stalling. This is the rule tools/pipeline.py applies, as an importable module (the pipeline still carries its
own copy). valve_decision is a pure function so the rule can be tested; tools/test_memvalve.py does. Import it from a script run with
`python3 -I` by adding the tools directory to sys.path first.
"""
import os, signal, subprocess, time


def mem_avail_gib():
    for l in open('/proc/meminfo'):
        if l.startswith('MemAvailable:'): return int(l.split()[1]) / 2**20


def mem_psi_some10():
    return float(open('/proc/pressure/memory').readline().split('avg10=')[1].split()[0])


def descendants(pid):
    out = [pid]
    for c in subprocess.run(['pgrep', '-P', str(pid)], capture_output=True, text=True).stdout.split():
        out += descendants(int(c))
    return out


def valve_decision(paused, calm, psi, avail, psi_pause=25, psi_resume=8, min_avail=3, resume_avail=4.5):
    """Returns (action, new_calm); action is 'pause', 'resume' or None."""
    if not paused:
        return ('pause', 0) if (psi > psi_pause or avail < min_avail) else (None, 0)
    calm = calm + 1 if (psi < psi_resume and avail > resume_avail) else 0
    return ('resume', 0) if calm >= 3 else (None, calm)


class MemoryValve:
    def __init__(self, root, log=print, notify=None, **limits):
        self.root, self.log, self.notify, self.limits = root, log, notify, limits
        self.paused, self.calm, self.since, self.noted = [], 0, 0, 0

    def step(self):
        psi, av = mem_psi_some10(), mem_avail_gib()
        act, self.calm = valve_decision(bool(self.paused), self.calm, psi, av, **self.limits)
        if act == 'pause':
            self.paused = descendants(self.root); self.since = self.noted = time.time()
            for _ in range(2):
                for q in descendants(self.root):
                    try: os.kill(q, signal.SIGSTOP)
                    except OSError: pass
                time.sleep(0.3)
            self.log(f"memory valve: froze build ({len(self.paused)} processes) at pressure {psi:.0f}% and {av:.1f} GiB available")
        elif act == 'resume':
            for q in sorted(descendants(self.root), reverse=True):
                try: os.kill(q, signal.SIGCONT)
                except OSError: pass
            self.log(f"memory valve: thawed build after {time.time() - self.since:.0f} s (pressure {psi:.0f}%, {av:.1f} GiB available)")
            self.paused = []
        elif self.paused and time.time() - self.noted > 600:
            self.noted = time.time()
            if self.notify: self.notify(f'build frozen {time.time() - self.since:.0f} s by the memory valve; {av:.1f} GiB available, pressure {psi:.0f}%')

    def release(self):
        if self.paused:
            for q in descendants(self.root):
                try: os.kill(q, signal.SIGCONT)
                except OSError: pass
