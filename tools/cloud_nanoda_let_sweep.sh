#!/bin/bash
# cloud_nanoda_let_sweep: A/B the nanoda "let" patch against its base on every configuration, stopping at the first regression; safe on a spot instance.
#
# Purpose: nanoda_lib issue 62. base is upstream master 8199c74 and patched is the same source with infer_let changed to check the body with a
# free variable that has a value, as Lean's kernel does, plus the Nat.succ free-variable guard of issue 61 (ext/bin/nanoda_8199c74 and
# ext/bin/nanoda_letB). Runs tools/nanoda_ab.py with --stop-on-regression --resume over the lists in scratch/ab-lists (tier 2: the 15
# configurations that failed with the pinned build; tier 3: the other 381 at 4 threads; tier 4: the 20 largest at 8 threads) as a single schedule in the
# order 4, 2, 3: the largest configurations are the likeliest to expose a problem and the longest, so they start first, and the smaller ones fill in the
# free cores and memory as the big ones finish (see the scheduling notes in tools/nanoda_ab.py).
# Results go to results/nanoda-ab-let.jsonl, one line per finished run.
# Spot instances: the script can be started again at any time (tools/cloud_boot_hook.sh does so at every boot) and continues where the output file says
# it stopped; only the configurations in flight when the instance was reclaimed run again. A watcher syncs the output to s3://BUCKET/ab-let/ every 5
# minutes and at once when the metadata service announces a reclaim. It does nothing unless results/nanoda-ab-let.GO exists, so the sweep never starts
# before the builds have been checked. At the end (all tiers done, or a regression found) it writes results/nanoda-ab-let.DONE, syncs and stops the
# instance by itself; a stopped persistent spot request does not restart the instance.
# Usage: cloud_nanoda_let_sweep.sh [BUCKET]
BUCKET=${1:-experiment-618-openai-math-a2ea0dcc}
cd "$(dirname "$0")/.." || exit 1
export PATH=$HOME/.elan/bin:$PATH
# nanoda_ab.py runs every stage with `systemd-run --user`, which needs the user's systemd manager and its bus: it exists without a login session
# only if lingering is on (sudo loginctl enable-linger ubuntu, done by tools/cloud_spot_launch.sh), and from a boot hook the variable must be set
export XDG_RUNTIME_DIR=/run/user/$(id -u)
for _ in $(seq 60); do [ -S "$XDG_RUNTIME_DIR/bus" ] && break; sleep 2; done
[ -S "$XDG_RUNTIME_DIR/bus" ] || { echo "$(date -Is) no user bus at $XDG_RUNTIME_DIR/bus; not starting"; exit 1; }
OUT=results/nanoda-ab-let.jsonl
[ -f results/nanoda-ab-let.GO ] || { echo "no results/nanoda-ab-let.GO; not starting"; exit 0; }
[ -f results/nanoda-ab-let.DONE ] && { echo "already done"; exit 0; }
pgrep -f "^python3 -I tools/nanoda_ab.py --build" > /dev/null && { echo "already running"; exit 0; }
python3 -I tools/nanoda_ab.py --print-host >> $OUT   # which machine (instance, type, lifecycle, CPU) this start of the sweep runs on
sync_out() { aws s3 cp $OUT s3://$BUCKET/ab-let/nanoda-ab-let.jsonl --only-show-errors; }
watcher() {
  while true; do
    tok=$(curl -s -m 2 -X PUT -H "X-aws-ec2-metadata-token-ttl-seconds: 60" http://169.254.169.254/latest/api/token)
    code=$(curl -s -m 2 -o /dev/null -w '%{http_code}' -H "X-aws-ec2-metadata-token: $tok" http://169.254.169.254/latest/meta-data/spot/instance-action)
    if [ "$code" = 200 ]; then echo "$(date -Is) spot reclaim announced"; sync_out; sleep 150; fi
    for _ in $(seq 30); do sleep 10; [ "$code" = 200 ] && break; done
    sync_out
  done
}
watcher &
WATCH=$!
B="--build base=ext/bin/nanoda_8199c74 --build patched=ext/bin/nanoda_letB"
# One ordered list with each tier's own settings (NAME:THREADS:MEM:TIMEOUT): the 20 largest first (8 threads, 60G, 2 h), then the 15 old failures, then the rest
# (4 threads, 30G, 30 min). The scheduler of nanoda_ab.py starts configurations in this order within a budget of 32 threads and 235 GiB of memory caps, and lets
# smaller ones start in the free space while a big one waits for room, so the machine stays busy as the big runs finish.
ALL=scratch/ab-lists/ab-all.txt
{ sed '/^$/d; s/$/:8:60G:7200/' scratch/ab-lists/ab-t4.txt; sed '/^$/d; s/$/:8:60G:3600/' scratch/ab-lists/ab-t2.txt; sed '/^$/d; s/$/:4:30G:1800/' scratch/ab-lists/ab-t3.txt; } > $ALL
sweep() {
  echo "$(date -Is) sweep start"
  python3 -I tools/nanoda_ab.py $B --stop-on-regression --resume --jobs 12 --cpus 32 --mem-budget 235 --out $OUT @$ALL
  rc=$?
  if [ $rc = 3 ]; then echo "$(date -Is) systemd-run failed, probably a spot reclaim"; return 3; fi
  if grep -q '"regression"' $OUT; then echo "$(date -Is) regression found, stopping"; return 1; fi
}
# If systemd-run fails the machine is probably being reclaimed: wait for that (do not stop the instance ourselves, a self-initiated stop disables the
# persistent spot request) and try again a few times if it is still here.
for attempt in 1 2 3; do
  sweep
  [ $? = 3 ] || break
  sleep 240
done
echo "$(date -Is) sweep ended"
kill $WATCH
sync_out
# DONE only if every configuration of the three lists has a record for both builds (or a regression stopped the run); otherwise stop the machine without it
MISSING=$(python3 -I - <<'PY'
import json
done = {}
for l in open('results/nanoda-ab-let.jsonl'):
    r = json.loads(l)
    if r.get('label') and 'rc' in r: done.setdefault(r['config'], set()).add(r['label'])
names = [l.strip() for t in (2, 3, 4) for l in open(f'scratch/ab-lists/ab-t{t}.txt') if l.strip()]
print(sum(1 for n in names if len(done.get(n, ())) < 2))
PY
)
if grep -q '"regression"' $OUT || [ "$MISSING" = 0 ]; then date -Is > results/nanoda-ab-let.DONE; else echo "$(date -Is) $MISSING configurations without a complete record; not marking done"; fi
sudo shutdown -h +2 "cloud_nanoda_let_sweep ended"
