#!/bin/bash
# build_nanoda_big_stack.sh [BASE]: rebuild nanoda with a 1 GiB checker-thread stack instead of 16 MiB, and install it as ext/bin/nanoda_bin.
# Purpose: with the pinned nanoda_lib (3a24072) the second kernel dies with "thread 'thread_1' has overflowed its stack ... nanoda exited with
# 134" on some exports (seen on DirectedFeedback and UniqueGamesTheorem; Lean's own kernel accepts them), and Comparator reports that as a
# rejection. The stack size is a compile-time constant (STACK_SIZE in src/lib.rs, 16 MiB, set with thread::Builder::stack_size, so
# RUST_MIN_STACK has no effect). The stack is virtual memory, used only as it grows, so raising it costs nothing for the checks that did not need it.
# This is a local change, not upstream: it edits src/lib.rs in ext/nanoda_lib and keeps the original binary as ext/bin/nanoda_bin.stack16MiB.
# The swap is atomic (rename), so a check that is running keeps the old binary until it ends. Idempotent.
set -euo pipefail
BASE=${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}; N=$BASE/ext/nanoda_lib
[ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
sed -i 's/pub(crate) const STACK_SIZE: usize = 16_777_216;/pub(crate) const STACK_SIZE: usize = 1_073_741_824;/' "$N/src/lib.rs"
grep -n 'STACK_SIZE: usize' "$N/src/lib.rs"
(cd "$N" && cargo build --release 2>&1 | tail -2)
[ -f "$BASE/ext/bin/nanoda_bin.stack16MiB" ] || cp "$BASE/ext/bin/nanoda_bin" "$BASE/ext/bin/nanoda_bin.stack16MiB"
cp "$N/target/release/nanoda_bin" "$BASE/ext/bin/nanoda_bin.new" && mv "$BASE/ext/bin/nanoda_bin.new" "$BASE/ext/bin/nanoda_bin"
echo "installed $(ls -l "$BASE/ext/bin/nanoda_bin" | cut -c1-60)"
