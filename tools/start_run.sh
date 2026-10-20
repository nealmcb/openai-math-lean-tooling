#!/bin/bash
# start_run.sh: (re)start the overnight run after a reboot or a stop: recover orphaned check records, then open a detached tmux session
# 'overnight' with windows pipeline, status and idleguard. Does nothing to any other tmux session. The pipeline resumes from
# results/cmp-all/all.jsonl and runs with the memory protections (valve, 6 compile slots, 20 GiB start gate, 2 check workers).
# Needs ext/ (tools and ext/sysroot-throttled) in place; see MANIFEST.txt.
B=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd); cd $B
tmux has-session -t overnight 2>/dev/null && { echo "tmux session 'overnight' already exists"; exit 1; }
python3 -I tools/recover_records.py | tail -1
ENVSET='cd '"$B"' && export PATH=$PWD/ext/bin:$PWD/ext/lean4export/.lake/build/bin:$HOME/.elan/bin:$PATH'
tmux new-session -d -s overnight -n pipeline "$ENVSET && python3 -I tools/pipeline.py 2>&1 | tee -a results/cmp-all/pipeline.out; echo pipeline-exited; sleep 86400"
tmux new-window -d -t overnight -n status "cd $B && while true; do python3 tools/overnight_status.py; sleep 600; done"
tmux new-window -d -t overnight -n idleguard "cd $B && python3 -u -I tools/idle_guard.py 2>&1 | tee -a results/cmp-all/idle_guard.out"
echo "started tmux session 'overnight' (pipeline, status, idleguard) at $(date -Is)" | tee -a results/cmp-all/driver.log
