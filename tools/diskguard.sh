#!/bin/bash
# diskguard: PAUSE (SIGSTOP, not kill) a build's process tree when free space on a
# filesystem falls below a threshold, so the user can free space and review.
# Resume with: kill -CONT -- <pids listed in PAUSED file>  (or tools/diskguard.sh --resume)
# Usage: diskguard.sh MOUNT MIN_FREE_GIB PATTERN   (PATTERN matched against process cmdlines by pgrep -f)
if [ "$1" = "--resume" ]; then
  [ -f "$2" ] && xargs -r kill -CONT < "$2" && rm -f "$2" && echo resumed; exit; fi
base=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mnt=$1; min=$2; pat=$3; flag=$base/logs/PAUSED
while true; do
  free=$(df -BG --output=avail "$mnt" | tail -1 | tr -dc 0-9)
  if [ "$free" -lt "$min" ] && [ ! -f "$flag" ]; then
    pgrep -f "$pat" | grep -vx "$$" > "$flag"
    xargs -r kill -STOP < "$flag"
    echo "$(date -Is) PAUSED at ${free}G free; pids in $flag" >> $base/logs/diskguard.log
  fi
  sleep 10
done
