#!/bin/bash
# aws_admin_guard_setup: the one-time account setup behind tools/cloud_guard.sh, which the restricted "experiment" user cannot do.
#
# Purpose: 2026-11-19, after an unguarded spot instance idled six days (~$33). Run once, by Neal, with an administrator profile:
#  1. create the service-linked role AWSServiceRoleForCloudWatchEvents, which CloudWatch alarms need to stop or terminate an EC2
#     instance (cloud_guard.sh arm failed with "not authorized to perform: iam:CreateServiceLinkedRole" without it);
#  2. add a daily cost budget (DAILY_LIMIT dollars, default 10) that emails when a day's actual spend exceeds it, sent to the same
#     subscribers as the existing monthly budget experiment-monthly-100. The monthly budget alone reacts too slowly to a machine
#     costing a few dollars a day. Never prints the subscriber addresses.
# Idempotent: an existing role or budget is reported and left alone.
# Usage: [DAILY_LIMIT=10] aws_admin_guard_setup.sh [ADMIN_PROFILE=default]
A="--profile ${1:-default}"; ACCT=952867749991; LIMIT=${DAILY_LIMIT:-10}
if aws iam get-role $A --role-name AWSServiceRoleForCloudWatchEvents > /dev/null 2>&1; then echo "role exists"
else aws iam create-service-linked-role $A --aws-service-name events.amazonaws.com --query Role.Arn --output text || exit 1; fi
if aws budgets describe-budget $A --account-id $ACCT --budget-name experiment-daily > /dev/null 2>&1; then echo "budget experiment-daily exists"
else
  S=$(aws budgets describe-subscribers-for-notification $A --account-id $ACCT --budget-name experiment-monthly-100 \
    --notification NotificationType=ACTUAL,ComparisonOperator=GREATER_THAN,Threshold=50,ThresholdType=PERCENTAGE --query Subscribers --output json) || exit 1
  aws budgets create-budget $A --account-id $ACCT \
    --budget "{\"BudgetName\":\"experiment-daily\",\"BudgetLimit\":{\"Amount\":\"$LIMIT\",\"Unit\":\"USD\"},\"TimeUnit\":\"DAILY\",\"BudgetType\":\"COST\"}" \
    --notifications-with-subscribers "[{\"Notification\":{\"NotificationType\":\"ACTUAL\",\"ComparisonOperator\":\"GREATER_THAN\",\"Threshold\":100,\"ThresholdType\":\"PERCENTAGE\"},\"Subscribers\":$S}]" \
    && echo "budget experiment-daily created: \$$LIMIT/day, same subscribers as experiment-monthly-100"
fi
