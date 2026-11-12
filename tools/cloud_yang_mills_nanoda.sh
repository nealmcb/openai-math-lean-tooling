#!/bin/bash
# cloud_yang_mills_nanoda: on an isolated scratch instance (tools/cloud_spot_scratch_launch.sh), build the October 2026 OpenAI Yang-Mills
# Lean submission as the Yang-Mills group's package pins it, export the Comparator target with their pinned lean4export, and check the
# export with nanoda, a second kernel independent of Lean's.
#
# Purpose: the group's assessment (yang-mills-group/YM, docs/assessment-1.pdf, 2026-11-10) checked YangMills.jointExistence with
# Comparator and Lean's kernel only ("An additional external kernel implementation was not used"). Steps, each resumable:
#   1. clone yang-mills-group/YM at REV and run its integrity check (scripts/verify.py integrity: every file against its hash);
#   2. their build stage (scripts/verify.py build: Mathlib cache, lake build WilsonReference WilsonConstruction in submission/);
#   3. lean4export at their pinned commit (verification/tool-pins.json), built with its own toolchain;
#   4. tools/nanoda_ab.py on their verification/submission.json (the solution's export, with Comparator's declaration list), first with
#      the nanoda build MASTER at its default stack, then with RECOMMENDED (PR 71 + Nat.succ guard) at a 64 MiB stack.
# Writes OUT/{driver.log,nanoda.jsonl,nanoda-logs/,DONE} and shuts the machine down at the end. Untrusted code: run it only on a
# machine with no AWS credentials, no metadata service and none of our data.
# Usage: cloud_yang_mills_nanoda.sh   (env REV, OUT, MASTER, RECOMMENDED, THREADS, MEM override the defaults)
W=/home/ubuntu/work; T=$W/tooling
REV=${REV:-55ba9fc362}; OUT=${OUT:-$T/results/yang-mills-20261028}
MASTER=${MASTER:-$T/bin/nanoda.master}; RECOMMENDED=${RECOMMENDED:-$T/bin/nanoda.master+71+guard}
THREADS=${THREADS:-16}; MEM=${MEM:-50G}
mkdir -p "$OUT"; [ -f "$OUT/DONE" ] && { echo "already done"; exit 0; }
exec 9> "$OUT/lock"; flock -n 9 || { echo "already running"; exit 0; }
export PATH=$HOME/.elan/bin:$PATH XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
log() { echo "$(date -Is) $*" | tee -a "$OUT/driver.log"; }
step() { log "$1: start"; shift; "$@" >> "$OUT/steps.log" 2>&1; local rc=$?; log "exit $rc"; return $rc; }
PKG=$W/YM/submissions/openai-20261028
log "start: YM $REV, $(nproc) CPUs, $(free -g | awk '/Mem/{print $2}') GiB, disk $(df -h $W | tail -1 | awk '{print $4}') free"
[ -d $W/YM ] || step clone git clone -q https://github.com/yang-mills-group/YM $W/YM || exit 1
git -C $W/YM checkout -q "$REV" && log "YM at $(git -C $W/YM rev-parse HEAD)"
(cd $PKG && step "1 integrity" python3 scripts/verify.py integrity) || exit 1
(cd $PKG && step "2 build" python3 scripts/verify.py build) || exit 1
E=$(python3 -I -c 'import json,sys; t=[x for x in json.load(open(sys.argv[1]))["tools"] if x["name"]=="lean4export"][0]; print(t["revision"])' $PKG/verification/tool-pins.json)
if [ ! -x $W/lean4export/.lake/build/bin/lean4export ]; then
  [ -d $W/lean4export ] || git clone -q https://github.com/leanprover/lean4export $W/lean4export
  git -C $W/lean4export checkout -q "$E"; (cd $W/lean4export && step "3 lean4export $E" lake build) || exit 1
fi
log "lean4export $(git -C $W/lean4export rev-parse HEAD), toolchain $(cat $W/lean4export/lean-toolchain)"
for b in "master=$MASTER:" "master+71+guard.64M=$RECOMMENDED:67108864"; do
  label_path=${b%:*}; stack=${b##*:}
  step "4 nanoda $label_path" python3 -I $T/tools/nanoda_ab.py --build "$label_path" --project $PKG/submission --configs $PKG/verification \
    --exporter $W/lean4export/.lake/build/bin ${stack:+--stack-bytes $stack} --jobs 1 --out "$OUT/nanoda.jsonl" --resume submission:$THREADS:$MEM:14400
  rc=$(tail -1 "$OUT/driver.log" | awk '{print $NF}'); [ "$rc" = 3 ] && { log "machine failure under the run; not marking done"; exit 3; }
done
date -Is > "$OUT/DONE"; sync
log "shutting down in 3 minutes"; sudo shutdown -h +3 "cloud_yang_mills_nanoda ended"
