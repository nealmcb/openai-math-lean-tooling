#!/bin/bash
# cloud_spot_scratch_launch: start an isolated spot instance for building untrusted Lean code: no data volume, no IAM role, the instance
# metadata service switched off, and its own new scratch disk mounted at /home/ubuntu/work.
#
# Purpose: compiling a Lean project can run arbitrary code (#eval, macros, build scripts). For third-party submissions (2026-11-10: the
# OpenAI Yang-Mills Lean code) the build must not reach the openai/math data volume or any AWS credentials. The instance comes from the
# usual image (elan, Python), keeps the experiment security group (SSH from the laptop only), and is a persistent spot request with stop
# behaviour, so a reclaim stops it with its disks and AWS starts it again when capacity returns. The scratch disk (gp3, SIZE GiB) is
# deleted when the instance is terminated. Prints "up INSTANCE ADDRESS" or exits 1 when no type in TYPES has capacity.
# Usage: cloud_spot_scratch_launch.sh [SIZE_GIB=150]   (env TYPES: instance types to try in order)
SIZE=${1:-150}
P="--profile experiment --region us-east-1"
AMI=ami-06544a48507ad4250
KEY=$HOME/.ssh/experiment-pilot.pem
TYPES=${TYPES:-"r6a.8xlarge c7a.8xlarge c6a.8xlarge r7a.8xlarge m6a.8xlarge m7a.8xlarge"}
for t in $TYPES; do
  ID=$(aws ec2 run-instances $P --image-id $AMI --instance-type "$t" --key-name experiment-pilot --security-group-ids sg-05f8c8a6d799b6322 \
    --subnet-id subnet-0dad3b19ced520bc0 --metadata-options HttpEndpoint=disabled \
    --block-device-mappings "[{\"DeviceName\":\"/dev/sdg\",\"Ebs\":{\"VolumeSize\":$SIZE,\"VolumeType\":\"gp3\",\"DeleteOnTermination\":true}}]" \
    --instance-market-options '{"MarketType":"spot","SpotOptions":{"SpotInstanceType":"persistent","InstanceInterruptionBehavior":"stop"}}' \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=experiment-scratch},{Key=project,Value=experiment}]' \
    --query 'Instances[0].InstanceId' --output text 2>/dev/null) && break
  echo "$t: no capacity"; ID=
done
[ -n "$ID" ] || { echo "no capacity"; exit 1; }
aws ec2 wait instance-running $P --instance-ids "$ID"
IP=$(aws ec2 describe-instances $P --instance-ids "$ID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
SSH="ssh -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o ConnectionAttempts=20"
# the image's fstab mounts the openai/math data volume with nofail; it is absent here. Format and mount the scratch disk (the second
# NVMe device that has no partitions and is not the root disk), and add it to fstab so it is mounted again after a stop.
$SSH ubuntu@"$IP" 'set -e; D=$(lsblk -dpno NAME,TYPE | awk "\$2==\"disk\"{print \$1}" | while read d; do [ -z "$(lsblk -no MOUNTPOINT $d | tr -d " \n")" ] && [ "$(lsblk -no NAME $d | wc -l)" = 1 ] && echo $d; done | head -1)
  echo "scratch disk $D"; sudo mkfs.ext4 -q -L scratch "$D"; sudo mkdir -p /home/ubuntu/work
  echo "LABEL=scratch /home/ubuntu/work ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab >/dev/null; sudo mount /home/ubuntu/work
  sudo chown ubuntu: /home/ubuntu/work; crontab -r 2>/dev/null || true; df -h /home/ubuntu/work | tail -1
  # the image carries the AWS CLI cache of the instance it was made from; nothing on this machine should hold AWS credentials
  rm -rf ~/.aws/cli/cache ~/.r2env
  c=$(curl -s -m 3 -o /dev/null -w "%{http_code}" http://169.254.169.254/latest/meta-data/); [ "$c" = 403 ] || [ "$c" = 000 ] && echo "metadata service off (HTTP $c)" || { echo "metadata service answers HTTP $c"; exit 1; }' || exit 1
echo "up $ID $IP"
