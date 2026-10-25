#!/bin/bash
# cloud_boot_hook: at every boot of the experiment instance, wait for the data volume and start the nanoda let sweep again.
#
# Purpose: with a persistent spot request whose interruption behaviour is "stop", a reclaimed instance is stopped and started again later with
# its disks. This script lives on the root volume (copy it to the ubuntu home directory and add `@reboot /home/ubuntu/cloud_boot_hook.sh` to its
# crontab, see tools/cloud_spot_launch.sh); it waits for /home/srv to be mounted, then starts tools/cloud_nanoda_let_sweep.sh, which resumes from
# its output file and does nothing once the sweep is done.
# Usage: cloud_boot_hook.sh
SWEEP=/home/srv/s/math/openai-math/tools/cloud_nanoda_let_sweep.sh
for _ in $(seq 120); do mountpoint -q /home/srv && break; sleep 5; done
mountpoint -q /home/srv || { echo "$(date -Is) /home/srv not mounted" >> /home/ubuntu/boot-hook.log; exit 1; }
echo "$(date -Is) boot: starting sweep" >> /home/ubuntu/boot-hook.log
nohup setsid "$SWEEP" >> /home/srv/s/math/openai-math/results/nanoda-ab-let.out 2>&1 < /dev/null &
