#!/bin/bash
# cloud_spot_launch: start the experiment instance as a persistent spot instance with the existing data volume, and install the boot hook.
#
# Purpose: run the long nanoda sweeps (tools/cloud_nanoda_let_sweep.sh) at the spot price instead of the on-demand price. The root volume comes from an
# image of the on-demand instance (without the data volume), the data volume vol-... (250 GB, us-east-1c) is attached afterwards and mounted through
# its fstab entry. The spot request is persistent with interruption behaviour "stop": when capacity is reclaimed the instance stops with its disks and
# starts again when capacity returns, and tools/cloud_boot_hook.sh (installed here in the ubuntu crontab) resumes the sweep. Prints the public address.
# Runs from the laptop with the AWS profile "experiment"; the key file, security group and subnet are those of the on-demand instance.
# Usage: [EXISTING_INSTANCE=i-...] cloud_spot_launch.sh AMI_ID [INSTANCE_TYPE=r7a.8xlarge]   (EXISTING_INSTANCE skips the launch and continues with that instance)
AMI=$1; TYPE=${2:-r7a.8xlarge}
P="--profile experiment --region us-east-1"
VOL=vol-0a293b81f0a1ec854
KEY=$HOME/.ssh/experiment-pilot.pem
HERE=$(dirname "$(readlink -f "$0")")
ID=${EXISTING_INSTANCE:-$(aws ec2 run-instances $P --image-id "$AMI" --instance-type "$TYPE" --key-name experiment-pilot --security-group-ids sg-05f8c8a6d799b6322 \
  --subnet-id subnet-0dad3b19ced520bc0 --iam-instance-profile Name=experiment-instance-role \
  --instance-market-options '{"MarketType":"spot","SpotOptions":{"SpotInstanceType":"persistent","InstanceInterruptionBehavior":"stop"}}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=experiment-spot},{Key=project,Value=experiment}]' \
  --query 'Instances[0].InstanceId' --output text)} || exit 1
echo "instance $ID"
aws ec2 wait instance-running $P --instance-ids "$ID"
# a stopped instance (the on-demand one) may still hold the data volume: detach it there first
OLD=$(aws ec2 describe-volumes $P --volume-ids $VOL --query 'Volumes[0].Attachments[0].InstanceId' --output text)
if [ "$OLD" != None ] && [ "$OLD" != "$ID" ]; then aws ec2 detach-volume $P --volume-id $VOL > /dev/null; aws ec2 wait volume-available $P --volume-ids $VOL; fi
aws ec2 attach-volume $P --volume-id $VOL --instance-id "$ID" --device /dev/sdf > /dev/null || exit 1
aws ec2 wait volume-in-use $P --volume-ids $VOL
IP=$(aws ec2 describe-instances $P --instance-ids "$ID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo "address $IP"
SSH="ssh -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o ConnectionAttempts=12"
$SSH ubuntu@"$IP" 'sudo mount -a; mountpoint /home/srv' || exit 1
scp -i "$KEY" -o StrictHostKeyChecking=no "$HERE/cloud_boot_hook.sh" ubuntu@"$IP":/home/ubuntu/cloud_boot_hook.sh || exit 1
$SSH ubuntu@"$IP" 'sudo loginctl enable-linger ubuntu; chmod +x /home/ubuntu/cloud_boot_hook.sh; (crontab -l 2>/dev/null | grep -v cloud_boot_hook; echo "@reboot /home/ubuntu/cloud_boot_hook.sh") | crontab -; crontab -l'
echo "$ID $IP" > "${CLAUDE_JOB_DIR:-/tmp}/tmp/spot-instance.txt"
