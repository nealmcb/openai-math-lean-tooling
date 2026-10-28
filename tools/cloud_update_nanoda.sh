#!/bin/bash
# cloud_update_nanoda: on the cloud machine, build the closures of the large configurations of an openai/math update and check them with nanoda.
#
# Purpose: the openai/math update fd4aeeb2ee -> 7ef5c0cc5 (2026-10-26) added configurations whose closures are too large for the laptop
# (HodgeConjectureCMAbelianVarieties/main: 33,429 new modules; SubexponentialSAT 3,092; LocalSmoothing 2,262; DefocusingNLS 1,284 changed).
# The data volume holds the full build of fd4aeeb2ee, so Lake compiles only new and changed modules. Steps:
#   1. a reaper deletes .lake/build/ir/**.setup.json files older than 5 minutes (Lake regenerates them and does not track them; 5.8 MB per
#      module would fill the disk), every minute while this runs;
#   2. lake build of the SMALL configurations (challenge and solution modules), then tools/nanoda_ab.py on them in the background with the
#      builds in BUILDS, while lake builds the BIG ones; then nanoda_ab.py on the big ones;
#   3. configurations where a build exits 134 (stack overflow at nanoda's 16 MiB) are rerun with the BUILDS64 variants;
#   4. sudo shutdown -h +3 at the end (the instance is a persistent spot request with stop behaviour, so the disk is kept).
# Output: results/update-7ef5c0c/ (cloud-builds.log, cloud-nanoda.jsonl, driver.log). Touch results/update-7ef5c0c/NOSHUTDOWN to keep the
# machine up at the end. Runs from the checkout this script is in.
# Resumable: after a spot reclaim, Lake rebuilds only what is missing and nanoda_ab.py --resume skips finished configurations; started from
# the boot hook (tools/cloud_boot_hook.sh with /home/ubuntu/boot-job naming this script) it continues by itself. It writes
# results/update-7ef5c0c/DONE at the end and then does nothing on later starts; a second copy exits at once.
# Usage: cloud_update_nanoda.sh   (env SMALL, BIG, BUILDS, BUILDS64, SPECS override the defaults below)
cd "$(dirname "$(readlink -f "$0")")/.." || exit 1
BASE=$PWD; R=$BASE/results/update-7ef5c0c; mkdir -p "$R"
export PATH=$BASE/ext/bin:$BASE/ext/lean4export/.lake/build/bin:$HOME/.elan/bin:$PATH
# nanoda_ab.py runs each stage with systemd-run --user; from the @reboot cron the user bus has to be found by hand (needs lingering on)
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
for _ in $(seq 60); do [ -S "$XDG_RUNTIME_DIR/bus" ] && break; sleep 2; done
SMALL=${SMALL:-"SubexponentialSAT LocalSmoothing DefocusingNLS"}
BIG=${BIG:-"HodgeConjectureCMAbelianVarieties/main"}
B=$BASE/scratch/bin
BUILDS=${BUILDS:-"--build master=$B/nanoda.master --build master+71=$B/nanoda.master+71"}
BUILDS64=${BUILDS64:-"--build master.64M=$B/nanoda.master.64M --build master+71.64M=$B/nanoda.master+71.64M"}
# NAME:THREADS:MEM:TIMEOUT for nanoda_ab.py; the Hodge closure is far larger than anything checked before
SPECS=${SPECS:-"HodgeConjectureCMAbelianVarieties/main:16:150G:28800 SubexponentialSAT:8:60G:14400 LocalSmoothing:8:60G:14400 DefocusingNLS:8:60G:14400"}
log() { echo "$(date -Is) $*" | tee -a "$R/driver.log"; }
spec() { for s in $SPECS; do [ "${s%%:*}" = "$1" ] && { echo "$s"; return; }; done; echo "$1"; }
modules() { for c in "$@"; do python3 -I -c 'import json,sys; c=json.load(open(sys.argv[1])); print(c["challenge_module"], c["solution_module"])' "src/lean/ComparatorChallenges/$c.json"; done; }
build() { log "lake build of $*"; (cd src/lean && lake build $(cd "$BASE" && modules "$@")) >> "$R/cloud-builds.log" 2>&1; local rc=$?; log "lake build exit $rc ($(grep -c 'Built ' "$R/cloud-builds.log") Built lines so far)"; return $rc; }
nanoda() { local label=$1; shift; log "nanoda_ab ($label) on $*"
  python3 -I tools/nanoda_ab.py $BUILDS --jobs 3 --cpus 32 --mem-budget 220 --out "$R/cloud-nanoda.jsonl" --resume $(for c in "$@"; do spec "$c"; done) >> "$R/driver.log" 2>&1
  local over; over=$(python3 -I -c 'import json,sys; print(" ".join(sorted({d["config"] for d in map(json.loads, open(sys.argv[1])) if d.get("rc") == 134 and d["config"] in sys.argv[2:]})))' "$R/cloud-nanoda.jsonl" "$@")
  if [ -n "$over" ]; then log "stack overflow at 16 MiB in: $over; rerunning with the 64 MiB builds"
    python3 -I tools/nanoda_ab.py $BUILDS64 --jobs 3 --cpus 32 --mem-budget 220 --out "$R/cloud-nanoda.jsonl" --resume $(for c in $over; do spec "$c"; done) >> "$R/driver.log" 2>&1; fi
  log "nanoda_ab ($label) done"; }

[ -f "$R/DONE" ] && { echo "already done ($R/DONE)"; exit 0; }
exec 9> "$R/lock"; flock -n 9 || { echo "already running"; exit 0; }
( while :; do find src/lean/.lake/build/ir -name '*.setup.json' -mmin +5 -delete 2>/dev/null; sleep 60; done ) & REAPER=$!
trap 'kill $REAPER 2>/dev/null' EXIT
log "start: openai/math $(git -C src rev-parse --short HEAD); disk $(df -h /home/srv | tail -1 | awk '{print $4}') free"
build $SMALL && { nanoda small $SMALL & NSMALL=$!; }
build $BIG && BIGOK=1
[ -n "$NSMALL" ] && wait "$NSMALL"   # (a bare `wait` would also wait for the reaper, forever)
[ -n "$BIGOK" ] && nanoda big $BIG
log "all done; disk $(df -h /home/srv | tail -1 | awk '{print $4}') free"
date -Is > "$R/DONE"
sync
[ -f "$R/NOSHUTDOWN" ] || { log "shutting down in 3 minutes"; sudo shutdown -h +3 "cloud_update_nanoda ended"; }
