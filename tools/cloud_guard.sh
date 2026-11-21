#!/bin/bash
# cloud_guard: make AWS itself stop paying for an idle instance, so a lost session cannot leave a machine running for days.
#
# Purpose: 2026-11-19, a Yang-Mills cache test instance (r7a.2xlarge spot) finished its 10-minute job on 2026-11-13 and then idled,
# relaunched by its persistent spot request, for ~154 h (~$33), because nothing but a returning Claude session would have stopped it.
# A CloudWatch alarm runs on AWS's side and needs no credentials on the instance (the isolated scratch machines have none).
#   arm ID [ACTION=stop] [IDLE_HOURS=2]  create alarm "idle-ACTION-ID": when the instance's maximum CPU stays below 5% for
#                                 IDLE_HOURS (5-minute basic-monitoring periods), CloudWatch runs ACTION on it. "stop" is the default
#                                 for our persistent spot instances: it ends the compute charges but keeps the disks, so an idle machine
#                                 holding results not yet copied off (an unconverted build) loses nothing, and an API stop leaves a
#                                 persistent request's instance stopped instead of relaunching it. "terminate" (destroys the disks) only
#                                 for one-time spot or on-demand instances with nothing worth keeping. Missing data (a stopped
#                                 instance) does not count as idle.
#   sweep                         delete the idle alarms whose instance is gone, then list every instance that is running, or stopped
#                                 but still holding disks, with its age and whether an alarm guards it, and every unattached
#                                 volume (still billed).
# Setup, once per account: the alarm's EC2 action needs the service-linked role AWSServiceRoleForCloudWatchEvents, which the
# experiment user cannot create; an administrator runs `aws iam create-service-linked-role --aws-service-name events.amazonaws.com`.
# Usage: cloud_guard.sh arm INSTANCE_ID [stop|terminate] [IDLE_HOURS] | cloud_guard.sh sweep
P="--profile experiment --region us-east-1"
case $1 in
arm)
  ID=${2:?instance id}; ACT=${3:-stop}; H=${4:-2}
  case $ACT in terminate|stop) ;; *) echo "action must be terminate or stop" >&2; exit 2;; esac
  aws cloudwatch put-metric-alarm $P --alarm-name "idle-$ACT-$ID" \
    --alarm-description "cloud_guard.sh: $ACT $ID after ${H} h with max CPU below 5%" \
    --namespace AWS/EC2 --metric-name CPUUtilization --dimensions Name=InstanceId,Value="$ID" \
    --statistic Maximum --period 300 --evaluation-periods $((H * 12)) --threshold 5 --comparison-operator LessThanThreshold \
    --treat-missing-data notBreaching --alarm-actions "arn:aws:automate:us-east-1:ec2:$ACT" || exit 1
  echo "armed: $ACT $ID after $H h idle";;
sweep)
  live=$(aws ec2 describe-instances $P --filters Name=instance-state-name,Values=pending,running,stopping,stopped \
    --query 'Reservations[].Instances[].InstanceId' --output text)
  for a in $(aws cloudwatch describe-alarms $P --alarm-name-prefix idle- --query 'MetricAlarms[].AlarmName' --output text); do
    id=${a##*-}; id=i-$id
    echo " $live " | grep -q " $id\b" || { aws cloudwatch delete-alarms $P --alarm-names "$a" && echo "deleted alarm $a (instance gone)"; }
  done
  alarms=$(aws cloudwatch describe-alarms $P --alarm-name-prefix idle- --query 'MetricAlarms[].AlarmName' --output text)
  aws ec2 describe-instances $P --filters Name=instance-state-name,Values=pending,running,stopped \
    --query 'Reservations[].Instances[].[InstanceId,State.Name,InstanceType,InstanceLifecycle,LaunchTime]' --output text |
  while read -r id state type life t; do
    age=$(( ($(date +%s) - $(date -d "$t" +%s)) / 3600 ))
    g=$(echo "$alarms" | tr "\t" "\n" | grep -- "-$id\$" || { [ "$state" = stopped ] && echo "(stopped: paying for disks only)" || echo UNGUARDED; })
    gib=$(aws ec2 describe-volumes $P --filters Name=attachment.instance-id,Values="$id" --query 'sum(Volumes[].Size)' --output text)
    echo "$state $id $type ${life/None/on-demand} launched ${age} h ago, ${gib} GiB of disks  $g"
  done
  # a volume that was detached and reattached loses DeleteOnTermination, so it outlives its instance (2026-11-20: the 150 GiB
  # Yang-Mills scratch disk was left behind this way)
  aws ec2 describe-volumes $P --filters Name=status,Values=available --query 'Volumes[].[VolumeId,Size,VolumeType,CreateTime]' --output text |
  while read -r v s t c; do echo "unattached $v $s GiB $t, created ${c%%T*}"; done;;
*) sed -n '2,22p' "$0"; exit 2;;
esac
