#!/bin/bash
# update_local_checks: build and Comparator-check configurations of a newer openai/math commit on the laptop, one at a time, using the OAI Lake cache.
#
# Purpose: after an openai/math update, check the configurations that need few modules compiled (tools/update_impact.py lists them) without
# a cloud machine. Builds go through tools/with_oai_cache.sh (unchanged modules come from the cache), and tools/run_comparator_batch.py runs
# each build and check in order, resumable, appending to OUT. Memory: the build runs in a scope capped at MEMMAX and the check in its own unit
# with the same cap, one after the other (laptop rule: one heavy job at a time, caps around 20G).
# Usage: [MEMMAX=20G] update_local_checks.sh OUT.jsonl CONFIG_NAME...   (CONFIG_NAME as in ComparatorChallenges/<name>.json without .json)
HERE=$(dirname "$(readlink -f "$0")")
BASE=${CHECKOUT:-$(dirname "$HERE")}
OUT=$(readlink -f "$1"); shift
MEMMAX=${MEMMAX:-20G}
export CHECKOUT=$BASE CHECK_MEMMAX=$MEMMAX COMPARATOR_BIN=$BASE/ext/comparator/.lake/build/bin/comparator
export PATH=$BASE/ext/bin:$BASE/ext/lean4export/.lake/build/bin:$HOME/.elan/bin:$PATH
exec systemd-run --user --scope -q -p MemoryMax="$MEMMAX" "$HERE/with_oai_cache.sh" python3 -I "$HERE/run_comparator_batch.py" "$BASE/src/lean" "$OUT" "$@"
