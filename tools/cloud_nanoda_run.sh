#!/bin/bash
# cloud_nanoda_run: on the cloud machine, run tools/nanoda_ab.py with one or more nanoda builds on configurations whose closures are
# already built, then shut the machine down.
#
# Purpose: a nanoda check on its own, outside Comparator, with nanoda_ab.py's records (full output in nanoda-logs/, the build's
# description, peak memory under a cap). Written 2026-11-06 for HodgeConjectureCMAbelianVarieties/main at openai/math 4eaee87, whose
# nanoda stage inside Comparator ended without a verdict. Resumable: nanoda_ab.py --resume skips configurations already recorded for
# every build. Writes RESULTS/NANODA-DONE at the end, but not when nanoda_ab.py reports that the machine failed under it (exit 3);
# started from the boot hook (FROM_BOOT=1) after that, it shuts the machine down after 10 minutes, since a persistent spot request
# restarts an instance that shut itself down (stop it from the laptop to disable the request).
# Usage: RESULTS=DIR BUILDS="LABEL=PATH ..." SPECS="NAME[:THREADS:MEM:TIMEOUT] ..." [CACHE_AFTER=1] cloud_nanoda_run.sh
#        (CACHE_AFTER=1 refreshes the Lake cache bundles afterwards, see tools/cloud_cache_update.sh)
cd "$(dirname "$(readlink -f "$0")")/.." || exit 1
BASE=$PWD; R=${RESULTS:?RESULTS}; mkdir -p "$R"
# (the 10 minutes leave time to log in and copy results: `shutdown +N` would block logins at once)
if [ -f "$R/NANODA-DONE" ]; then echo "already done"; [ -n "$FROM_BOOT" ] && { sleep 600; sudo shutdown -h now "cloud_nanoda_run already done"; }; exit 0; fi
exec 9> "$R/nanoda.lock"; flock -n 9 || { echo "already running"; exit 0; }
export PATH=$BASE/ext/bin:$BASE/ext/lean4export/.lake/build/bin:$HOME/.elan/bin:$PATH
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
for _ in $(seq 60); do [ -S "$XDG_RUNTIME_DIR/bus" ] && break; sleep 2; done
log() { echo "$(date -Is) $*" | tee -a "$R/nanoda-driver.log"; }
B=(); for b in ${BUILDS:?BUILDS}; do B+=(--build "$b"); done
log "start: openai/math $(git -C src rev-parse --short HEAD); builds $BUILDS; specs $SPECS"
python3 -I tools/nanoda_ab.py "${B[@]}" --jobs 1 --out "$R/nanoda.jsonl" --resume ${SPECS:?SPECS} >> "$R/nanoda-driver.log" 2>&1; rc=$?
log "nanoda_ab exit $rc"
[ $rc = 3 ] && { log "the machine failed under the run (exit 3: a reclaim?); not marking done, the boot hook resumes"; exit 3; }
date -Is > "$R/NANODA-DONE"; sync
# CACHE_AFTER=1: go on to build the rest of the library and convert it for the Lake cache (tools/cloud_cache_update.sh, which shuts down)
[ -n "$CACHE_AFTER" ] && { log "continuing with tools/cloud_cache_update.sh"; exec tools/cloud_cache_update.sh; }
log "shutting down in 3 minutes"; sudo shutdown -h +3 "cloud_nanoda_run ended"
