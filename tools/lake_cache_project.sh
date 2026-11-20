#!/bin/bash
# lake_cache_project: turn an up-to-date build of any Lake project into Lake artifact-cache bundles plus one mapping file, ready for
# tools/lake_cache_upload.sh.
#
# Purpose: preserve the compile of a project checked on a cloud machine (2026-11-12: the OpenAI Yang-Mills submission, Lean 4.32.0,
# 1.5 h of compiling) so others can download it instead of compiling. On an up-to-date workspace `lake build TARGETS -o MAP` with
# LAKE_ARTIFACT_CACHE=true compiles nothing; it bundles each module's outputs into OUT/cache/artifacts/<hash>.ltar and writes the
# mapping (input hash -> bundle) to OUT/map-all.jsonl, in the format of the project's own Lake version, so the same Lake can read it
# back. One Lake process suffices for projects of tens of thousands of modules; for openai/math use tools/lake_cache_convert.py, which
# splits OAI/ across processes. Lake also copies the dependencies' outputs (Mathlib's) into OUT/cache; only the bundles named in the
# mapping are uploaded. Prints the mapping's line count and how many modules Lake compiled (should be 0).
# Usage: lake_cache_project.sh PROJECT_DIR OUT_DIR TARGET...   (run with the project's lake on PATH)
P=$(readlink -f "${1:?project dir}"); OUT=$(readlink -m "${2:?out dir}"); shift 2; [ $# -gt 0 ] || { echo "no targets" >&2; exit 2; }
mkdir -p "$OUT/cache"
cd "$P" || exit 1
t0=$(date +%s)
LAKE_ARTIFACT_CACHE=true LAKE_CACHE_DIR="$OUT/cache" lake build "$@" -o "$OUT/map-all.jsonl" > "$OUT/convert.log" 2>&1; rc=$?
echo "lake exit $rc in $(( $(date +%s) - t0 )) s; Lake $(lake --version | head -1)"
echo "mapping: $(grep -c . "$OUT/map-all.jsonl") lines, first line: $(head -c 60 "$OUT/map-all.jsonl")"
echo "modules compiled during conversion: $(grep -c -E 'Built|Compiling' "$OUT/convert.log" | head -1) Built/Compiling lines (replayed ones excluded below)"
grep -E '^\S+ \[[0-9]+/[0-9]+\] Built ' "$OUT/convert.log" | head -3
exit $rc
