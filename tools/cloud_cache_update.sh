#!/bin/bash
# cloud_cache_update: on the cloud machine, finish building the whole OAI library at the current openai/math commit and convert it into Lake
# cache bundles, ready to upload as a new revision of the published cache (results/lake-cache-test/README.md).
#
# Purpose: refresh the public Lake cache after the openai/math update fd4aeeb2ee -> 7ef5c0cc5. The data volume holds the full fd4aeeb2ee
# build plus the closures of the 20 affected configurations; tools/update_impact.py --remaining counted 1,540 modules still to build.
# Steps: restore the published configuration files (the Comparator run had edited 14 of them; the edits are saved in
# results/update-7ef5c0c/cloud/compare-config-edits.patch); a reaper deletes .setup.json files older than 5 minutes (Lake regenerates
# them); `lake build OAI` (the root module imports the whole library); tools/lake_cache_convert.py into scratch/cache-REV; a check that
# the mapping covers every OAI module; then sudo shutdown -h +3 unless results/cache-REV/NOSHUTDOWN exists. Uploading is a separate,
# manual step (tools/push_r2_env.sh, then tools/lake_cache_upload.sh), because it publishes and needs the R2 credentials.
# Resumable: Lake rebuilds only what is missing and the converter converts what is missing; started from the boot hook
# (/home/ubuntu/boot-job), it continues after a spot reclaim, and does nothing once results/cache-REV/CACHE-DONE exists.
# Usage: cloud_cache_update.sh   (output: results/cache-REV/{driver.log,build.log,convert.log}, scratch/cache-REV/)
cd "$(dirname "$(readlink -f "$0")")/.." || exit 1
BASE=$PWD; REV=$(git -C src rev-parse --short=9 HEAD); R=$BASE/results/cache-$REV; OUT=$BASE/scratch/cache-$REV; mkdir -p "$R" "$OUT"
exec 9> "$R/lock"; flock -n 9 || { echo "already running"; exit 0; }
[ -f "$R/CACHE-DONE" ] && { echo "already done"; exit 0; }
export PATH=$HOME/.elan/bin:$PATH
log() { echo "$(date -Is) $*" | tee -a "$R/driver.log"; }
git -C src checkout -- lean/ComparatorChallenges
log "start: openai/math $REV, $(git -C src status --short | wc -l) changed files in the checkout, disk $(df -h /home/srv | tail -1 | awk '{print $4}') free, vm.max_map_count $(cat /proc/sys/vm/max_map_count)"
( while :; do find src/lean/.lake/build/ir -name '*.setup.json' -mmin +5 -delete 2>/dev/null; sleep 60; done ) & REAPER=$!
trap 'kill $REAPER 2>/dev/null' EXIT
log "lake build OAI"
(cd src/lean && lake build OAI) >> "$R/build.log" 2>&1; rc=$?
log "lake build exit $rc ($(grep -c 'Built ' "$R/build.log") Built lines)"
[ $rc = 0 ] || { log "build failed; not converting"; exit 1; }
log "convert"
python3 -I tools/lake_cache_convert.py src/lean "$OUT" --procs 8 >> "$R/convert.log" 2>&1; rc=$?
n_map=$(grep -c '^\[' "$OUT/map-all.jsonl" 2>/dev/null); n_mods=$(find src/lean/OAI -name '*.lean' | wc -l)
log "convert exit $rc; mapping lines $n_map; OAI source modules $n_mods (+1 root)"
[ $rc = 0 ] && [ "$n_map" -ge "$n_mods" ] || { log "mapping incomplete; not marking done"; exit 1; }
du -sh "$OUT" >> "$R/driver.log"
date -Is > "$R/CACHE-DONE"; sync
[ -f "$R/NOSHUTDOWN" ] || { log "shutting down in 3 minutes"; sudo shutdown -h +3 "cloud_cache_update ended"; }
