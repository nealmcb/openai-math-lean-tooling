#!/bin/bash
# cloud_long_launch: wait for the clean-rerun instance to stop, resize it, start it and launch tools/cloud_long_nanoda.sh in tmux "long" on it.
# Purpose: the long-check configurations need many cores and memory; the instance (behaviour "stop", data volume kept) is changed to TYPE only while stopped.
# Needs the AWS profile "experiment" and the key ~/.ssh/experiment-pilot.pem. Never terminates anything. Run as a background job and read its log.
# Usage: cloud_long_launch.sh INSTANCE_ID [TYPE=r7a.8xlarge]
IID=$1; TYPE=${2:-r7a.8xlarge}; export AWS_PAGER=; A="aws --profile experiment --region us-east-1"
KEY=~/.ssh/experiment-pilot.pem; base=$(cd "$(dirname "$0")/.." && pwd)
st() { $A ec2 describe-instances --instance-ids $IID --query 'Reservations[0].Instances[0].State.Name' --output text; }
until [ "$(st)" = stopped ]; do sleep 30; done
echo "$(date -Is) stopped; resizing to $TYPE"
$A ec2 modify-instance-attribute --instance-id $IID --instance-type "{\"Value\": \"$TYPE\"}" || { echo "resize failed"; exit 1; }
$A ec2 start-instances --instance-ids $IID >/dev/null || { echo "start failed"; exit 1; }
$A ec2 wait instance-running --instance-ids $IID
IP=$($A ec2 describe-instances --instance-ids $IID --query 'Reservations[0].Instances[0].PublicIpAddress' --output text); echo "$IP" > "$CLAUDE_JOB_DIR/tmp/newip-long.txt"
echo "$(date -Is) running at $IP"
S="ssh -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=10 ubuntu@$IP"
until $S 'mountpoint -q /home/srv'; do sleep 10; done
RB=${REMOTE_BASE:-/home/srv/s/math/openai-math}   # the checkout on the cloud machine (REMOTE_BASE overrides)
scp -i $KEY -o StrictHostKeyChecking=no "$base/tools/cloud_long_nanoda.sh" ubuntu@$IP:$RB/tools/
$S "tmux new-session -d -s long 'cd $RB && tools/cloud_long_nanoda.sh 2>&1 | tee results/long-nanoda.out'; sleep 5; tmux ls; nproc; free -g | head -2"
echo "$(date -Is) launched"
