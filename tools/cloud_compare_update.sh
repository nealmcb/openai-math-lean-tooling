#!/bin/bash
# cloud_compare_update: run Comparator, with nanoda in place of Lean's replay, on the configurations of an openai/math update that
# Comparator has not yet checked, so that each solution's statement is compared with the challenge's.
#
# Purpose: after the 7ef5c0cc5 update, 14 of the 20 affected configurations had been built (Lean's kernel checks every module during
# the build) and checked with nanoda alone (tools/nanoda_ab.py), which does not compare the solution with the challenge. This runs
# Comparator's own comparison on them. Lean's replay is skipped (patched Comparator, ext/comparator-skip,
# tools/patches/comparator-skip-builtin-kernel.patch) and nanoda checks the solution instead, with the binary in NANODA (passed to
# Comparator through COMPARATOR_NANODA; Comparator runs it with 4 threads). Steps:
#   1. in each config JSON, set "enable_nanoda": true and "skip_builtin_kernel": true, and save the edits as
#      results/update-7ef5c0c/compare-config-edits.patch (the checkout's configs are otherwise as published);
#   2. two tools/run_comparator_batch.py processes at once: BIG (Hodge) and the rest, largest first; each builds what is missing first,
#      records to results/update-7ef5c0c/compare.jsonl and keeps Comparator's full output in results/update-7ef5c0c/logs/;
#   3. sudo shutdown -h +3 at the end unless results/update-7ef5c0c/NOSHUTDOWN exists.
# Resumable: run_comparator_batch.py skips configurations already accepted in compare.jsonl. Writes COMPARE-DONE at the end.
# Usage: cloud_compare_update.sh   (env NANODA, BIG, REST override the defaults below)
cd "$(dirname "$(readlink -f "$0")")/.." || exit 1
BASE=$PWD; R=$BASE/results/update-7ef5c0c; mkdir -p "$R"
exec 9> "$R/compare.lock"; flock -n 9 || { echo "already running"; exit 0; }
[ -f "$R/COMPARE-DONE" ] && { echo "already done"; exit 0; }
export PATH=$BASE/ext/bin:$BASE/ext/lean4export/.lake/build/bin:$HOME/.elan/bin:$PATH
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
export COMPARATOR_BIN=$BASE/ext/comparator-skip/.lake/build/bin/comparator
export COMPARATOR_NANODA=${NANODA:-$BASE/scratch/bin/nanoda.master+71+guard.64M}
BIG=${BIG:-"HodgeConjectureCMAbelianVarieties/main"}
REST=${REST:-"SubexponentialSAT LocalSmoothing DefocusingNLS MaximalSeshadriConstants LittleFinitistic FinitisticAsymmetry KaplanskyStableFiniteness KaplanskyQuasitrace OccupiedOverlap ElementaryPositivity LogKodairaFiberNegative HarmonicGrowth SpinAngle"}
log() { echo "$(date -Is) $*" | tee -a "$R/compare-driver.log"; }
rm -f "$R/NOSHUTDOWN"   # left by the nanoda run; this run stops the machine itself

for c in $BIG $REST; do
  python3 -I - "src/lean/ComparatorChallenges/$c.json" <<'PY'
import json, sys
p = sys.argv[1]; c = json.load(open(p)); c.update(enable_nanoda=True, skip_builtin_kernel=True)
open(p, 'w').write(json.dumps(c, indent=2) + '\n')
PY
done
git -C src diff -- lean/ComparatorChallenges > "$R/compare-config-edits.patch"
log "start: comparator $(sha256sum "$COMPARATOR_BIN" | cut -c1-12), nanoda $(sha256sum "$COMPARATOR_NANODA" | cut -c1-12) ($(cat "$COMPARATOR_NANODA.info"))"
# one lake build of everything first, so the two batch processes below never compile the same module at once (their own builds are then no-ops)
MODS=$(for c in $BIG $REST; do python3 -I -c 'import json,sys; c=json.load(open(sys.argv[1])); print(c["challenge_module"], c["solution_module"])' "src/lean/ComparatorChallenges/$c.json"; done)
log "lake build of $(echo $MODS | wc -w) target modules"
(cd src/lean && lake build $MODS) >> "$R/compare-builds.log" 2>&1; log "lake build exit $? ($(grep -c 'Built ' "$R/compare-builds.log") Built lines)"
B=$BASE/tools/run_comparator_batch.py
python3 -I "$B" "$BASE/src/lean" "$R/compare.jsonl" $BIG >> "$R/compare-big.out" 2>&1 & P1=$!
python3 -I "$B" "$BASE/src/lean" "$R/compare.jsonl" $REST >> "$R/compare-rest.out" 2>&1 & P2=$!
wait $P1 $P2
log "done: $(python3 -I -c 'import json,sys,collections; print(dict(collections.Counter(json.loads(l).get("outcome") for l in open(sys.argv[1]))))' "$R/compare.jsonl")"
date -Is > "$R/COMPARE-DONE"; sync
[ -f "$R/NOSHUTDOWN" ] || { log "shutting down in 3 minutes"; sudo shutdown -h +3 "cloud_compare_update ended"; }
