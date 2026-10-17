#!/bin/bash
# lake_cache_shard.sh WORKSPACE MODULES_FILE OUTDIR: turn the already-built modules listed in MODULES_FILE (one module name per line, e.g. OAI.Algebra.Foo.Bar) into Lake artifact-cache files.
# Purpose: publish a per-module Lake cache of the openai/math build. With LAKE_ARTIFACT_CACHE=true, `lake build MODULES -o OUTDIR/map.jsonl` on an up-to-date workspace compiles nothing but
# writes the mapping (input hash -> .ltar bundle) and the bundles into its own cache dir OUTDIR/cache. Each shard has its own cache dir so several shards can run in parallel.
# Writes OUTDIR/{map.jsonl,build.log,time.txt}; the log is checked afterwards for "Compiling" lines (there must be none).
set -u
WS=$(realpath "${1:?workspace}"); LIST=$(realpath "${2:?modules file}"); OUT=${3:?outdir}; mkdir -p "$OUT/cache"; OUT=$(realpath "$OUT")
export LAKE_ARTIFACT_CACHE=true LAKE_CACHE_DIR="$OUT/cache"
cd "$WS" && /usr/bin/time -v -o "$OUT/time.txt" lake build $(cat "$LIST" | tr '\n' ' ') -o "$OUT/map.jsonl" > "$OUT/build.log" 2>&1
echo "exit $?" >> "$OUT/time.txt"
