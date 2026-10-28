#!/bin/bash
# cloud_spot_retry: one attempt to get a 32-vCPU spot machine in us-east-1c, where the data volume lives.
#
# Purpose: spot capacity in us-east-1c ran out on 2026-10-27 for every 32-vCPU type tried. Run this every hour or so (Neal chose waiting over
# moving the volume or paying on-demand). It first tries to start the existing stopped spot instance (r6a.8xlarge, whose persistent request is
# "disabled" after a user stop, so it never restarts by itself), then launches a new spot instance of each type in TYPES with
# tools/cloud_spot_launch.sh, which moves the data volume to it. Stops at the first success and prints "up INSTANCE ADDRESS"; prints
# "no capacity" and exits 1 otherwise. A new instance leaves the old stopped one in place (its root volume still costs a little).
# Usage: cloud_spot_retry.sh   (env TYPES overrides the list, OLD the stopped instance)
P="--profile experiment --region us-east-1"
OLD=${OLD:-i-08b8bc8ba3526bc1a}
TYPES=${TYPES:-"m6a.8xlarge r7a.8xlarge m7a.8xlarge c7a.8xlarge c6a.8xlarge m7i.8xlarge"}
HERE=$(dirname "$(readlink -f "$0")")
date -Is
if aws ec2 start-instances $P --instance-ids "$OLD" > /dev/null 2>&1; then
  aws ec2 wait instance-running $P --instance-ids "$OLD"
  IP=$(aws ec2 describe-instances $P --instance-ids "$OLD" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
  echo "$OLD $IP" > "${CLAUDE_JOB_DIR:-/tmp}/tmp/spot-instance.txt"
  echo "up $OLD $IP"; exit 0
fi
echo "$OLD: no capacity"
for t in $TYPES; do
  if out=$(bash "$HERE/cloud_spot_launch.sh" ami-06544a48507ad4250 "$t" 2>&1); then
    echo "$out" | tail -3; read -r ID IP < "${CLAUDE_JOB_DIR:-/tmp}/tmp/spot-instance.txt"; echo "up $ID $IP ($t)"; exit 0
  fi
  echo "$t: $(echo "$out" | grep -o 'InsufficientInstanceCapacity\|error.*' | head -1)"
  # a launch that got an instance but failed later (volume, ssh) needs a look, not another launch
  echo "$out" | grep -q '^instance i-' && { echo "launched but setup failed:"; echo "$out" | tail -5; exit 2; }
done
echo "no capacity"; exit 1
