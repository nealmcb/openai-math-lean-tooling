#!/usr/bin/env python3
"""restart_after_check: wait for one long Comparator check to finish, then restart the pipeline so it picks up new code.

Purpose: a running pipeline.py cannot reload its code, and restarting it kills any Comparator check in progress (a check cannot
resume; one config here has run for 6+ hours). This waits until the named config has a result in results/cmp-all/all.jsonl, then
until the old pipeline has archived the batch that check belonged to (a line "archived batch<id>" in driver.log, with a time limit),
and only then runs tools/stop_run.sh, closes the leftover tmux session and runs tools/start_run.sh. Losing the few seconds of
checks and build the old pipeline started in the meantime is acceptable; recover_records.py (run by start_run.sh) keeps their records.
It records what happened in results/cmp-all/restart_after_check.log and, as a flag for whoever supervises, writes
results/cmp-all/RESTARTED_AFTER_CHECK with the config's outcome and whether the new pipeline came up. It also sends a desktop
notification. If the pipeline is no longer running when the result arrives it just starts it.
Usage: restart_after_check.py CONFIG [--archive-wait 1200] [--results DIR] [--dry-run]
Run it outside any cgroup that holds the pipeline so the restart does not kill it, e.g.
  systemd-run --user --unit=restart-after-check --collect python3 -I tools/restart_after_check.py PlanarPacking
"""
import os, sys, json, time, subprocess, argparse, datetime
ap = argparse.ArgumentParser(); ap.add_argument('config'); ap.add_argument('--archive-wait', type=int, default=1200); ap.add_argument('--poll', type=int, default=30)
ap.add_argument('--results', help='results directory (default results/cmp-all)'); ap.add_argument('--dry-run', action='store_true', help='wait and log, but do not stop or start anything')
a = ap.parse_args()
base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')); R = a.results or base + '/results/cmp-all'
log = lambda m: open(R + '/restart_after_check.log', 'a').write(f"{datetime.datetime.now().astimezone().isoformat(timespec='seconds')} {m}\n")
sh = lambda *c: subprocess.run(c, cwd=base, capture_output=True, text=True)


def records():
    out = []
    if os.path.exists(R + '/all.jsonl'):
        for l in open(R + '/all.jsonl'):
            d = json.loads(l)
            if d['config'] == a.config: out.append(d)
    return out


def pipeline_up(): return sh('pgrep', '-f', '^python3 -I tools/pipeline.py').returncode == 0


seen = len(records())           # records from earlier attempts; the finished check adds one more
log(f"waiting for a new result for {a.config} (already {seen} records)")
while True:
    rs = records()
    if len(rs) > seen: d = rs[-1]; break
    time.sleep(a.poll)
outcome = d.get('outcome'); log(f"{a.config}: {outcome}, check {d.get('cmp_s')} s, {d.get('peak_rss_gib')} GiB")
bid = str(d.get('batch'))
t0 = time.time(); drv = R + '/driver.log'
while time.time() - t0 < a.archive_wait:
    if bid != 'None' and f"archived batch{bid}-" in open(drv, errors='replace').read(): log(f"batch {bid} archived"); break
    time.sleep(a.poll)
else: log(f"no archive line for batch {bid} within {a.archive_wait} s; restarting anyway")
if a.dry_run: log('dry run: would stop and start the pipeline now'); sys.exit(0)
if not pipeline_up(): log("pipeline is not running; starting it")
r = sh('tools/stop_run.sh'); log("stop_run: " + (r.stdout.strip() or r.stderr.strip())[-200:])
sh('tmux', 'kill-session', '-t', 'overnight')
r = sh('tools/start_run.sh'); log("start_run: " + (r.stdout.strip() or r.stderr.strip())[-300:])
time.sleep(20); up = pipeline_up()
msg = f"{a.config} {outcome} ({d.get('cmp_s')} s); pipeline restarted with new code: {'running' if up else 'NOT RUNNING - needs attention'}"
open(R + '/RESTARTED_AFTER_CHECK', 'w').write(msg + '\n'); log(msg)
sh('notify-send', 'Comparator pipeline', msg)
sys.exit(0 if up else 1)
