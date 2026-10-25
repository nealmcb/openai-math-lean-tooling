#!/bin/bash
# nanoda_tests: run nanoda_lib's own test suite on several source trees, including the tests marked #[ignore].
#
# Purpose: nanoda_lib issue 62. Before a build with the infer_let change (tools/patches/nanoda-let-fvar.patch) and the Nat.succ guard
# (tools/patches/nanoda-succ-fvars-guard.patch) is used for a sweep, its test suite has to pass as it does on stock upstream master.
# For each given source tree this runs `cargo test --release` and `cargo test --release -- --ignored` and writes the per-test lines
# and the result lines to OUTDIR/TREE-NAME.txt and OUTDIR/TREE-NAME-ignored.txt; the exit codes are on the last line of each file.
# Usage: nanoda_tests.sh OUTDIR TREE [TREE ...]
OUT=$(readlink -f "$1"); shift
mkdir -p "$OUT"
export PATH=$HOME/.cargo/bin:$PATH
for t in "$@"; do
  n=$(basename "$(readlink -f "$t")")
  ( cd "$t" || exit 1
    cargo test --release 2>&1 | grep -E "^test |test result|running|panicked|error" > "$OUT/$n.txt"; echo "exit ${PIPESTATUS[0]}" >> "$OUT/$n.txt"
    cargo test --release -- --ignored 2>&1 | grep -E "^test |test result|running|panicked|error" > "$OUT/$n-ignored.txt"; echo "exit ${PIPESTATUS[0]}" >> "$OUT/$n-ignored.txt" )
  echo "$n: $(grep -h 'test result' "$OUT/$n.txt" | head -1) | ignored: $(grep -h 'test result' "$OUT/$n-ignored.txt" | head -1)"
done
