#!/bin/bash
# pause.sh: instantly freeze the whole Comparator run (SIGSTOP) to quiet the fan and free the CPU. Resume with tools/resume.sh.
# Freezes: the pipeline, every descendant (lake, lean, vmamon, ...), and the sandboxed comparator systemd --user services.
# Memory stays allocated while paused. Timings recorded for work in flight will include the paused time.
base=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd); R=$base/results/cmp-all; list=$R/PAUSED_PIDS
[ -f $list ] && { echo "already paused ($(wc -l < $list) pids); use tools/resume.sh"; exit 0; }
root=$(pgrep -f '^python3 -I tools/pipeline.py' | head -1)
[ -z "$root" ] && { echo "no pipeline process found"; }
: > $list
descend() { local p; for p in $(pgrep -P "$1"); do echo $p; descend $p; done; }
for round in 1 2 3; do                      # repeat so children spawned meanwhile are caught
  pids="$root $(descend ${root:-0})"
  for u in $(systemctl --user list-units --state=running --no-legend 'run-*.service' 2>/dev/null | awk '{print $1}'); do
    pids="$pids $(systemctl --user show -p ControlGroup --value $u | xargs -I{} cat /sys/fs/cgroup{}/cgroup.procs 2>/dev/null | tr '\n' ' ')"
  done
  for p in $pids; do [ -n "$p" ] && kill -STOP $p 2>/dev/null && echo $p >> $list; done
done
sort -un $list -o $list
echo "$(date -Is) PAUSED $(wc -l < $list) processes" | tee -a $R/driver.log
