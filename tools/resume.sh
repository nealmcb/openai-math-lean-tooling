#!/bin/bash
# resume.sh: instantly resume everything frozen by tools/pause.sh (SIGCONT, children first).
base=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd); R=$base/results/cmp-all; list=$R/PAUSED_PIDS
[ -f $list ] || { echo "not paused"; exit 0; }
for p in $(sort -rn $list); do kill -CONT $p 2>/dev/null; done
rm -f $list; echo "$(date -Is) RESUMED" | tee -a $R/driver.log
