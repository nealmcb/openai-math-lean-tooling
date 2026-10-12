#!/bin/bash
# stop_run.sh: cleanly stop the overnight run (pipeline, its build, the monitors) before a reboot or an experiment.
# Sends SIGTERM to the pipeline's whole process tree, then SIGKILL to anything left after 5 s. Safe to repeat. Resume with tools/start_run.sh.
# Results, archives and finished build outputs are kept; an interrupted Lake build resumes from its finished modules.
PP=$(pgrep -f '^python3 -I tools/pipeline.py' | head -1)
[ -z "$PP" ] && { echo "pipeline is not running"; exit 0; }
python3 - "$PP" <<'P'
import subprocess, sys, os, signal, time
def desc(p):
    out = [p]
    for c in subprocess.run(['pgrep', '-P', str(p)], capture_output=True, text=True).stdout.split(): out += desc(int(c))
    return out
tree = desc(int(sys.argv[1]))
for q in tree:
    try: os.kill(q, signal.SIGTERM)
    except OSError: pass
time.sleep(5)
left = [q for q in tree if os.path.exists(f'/proc/{q}')]
for q in left:
    try: os.kill(q, signal.SIGKILL)
    except OSError: pass
print(f'stopped {len(tree)} processes ({len(left)} needed SIGKILL)')
P
tmux kill-window -t overnight:pipeline 2>/dev/null
echo "$(date -Is) STOPPED by tools/stop_run.sh" >> /home/srv/s/math/openai-math/results/cmp-all/driver.log
