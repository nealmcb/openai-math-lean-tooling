#!/bin/bash
# build_nanoda_variant: build one nanoda_bin from a nanoda_lib clone at a given commit, optionally with other branches merged or patches applied.
#
# Purpose: compare nanoda builds on new openai/math configurations (tools/nanoda_ab.py), e.g. upstream master alone and master with an open
# pull request merged, without touching ext/nanoda_lib. Each variant gets its own clone DIR (a git worktree would share ext/nanoda_lib's state).
# The binary is copied to OUT, and OUT.info records the commits and the merged refs/patches.
# stack:BYTES sets the checker threads' stack (STACK_SIZE in src/lib.rs, 16 MiB upstream); a run with one thread checks on the main thread,
# where `ulimit -s` applies instead. The clone is reset to REF on every run, so earlier edits do not carry over.
# Usage: build_nanoda_variant.sh DIR REF OUT [merge:REMOTE_URL#BRANCH ...] [patch:FILE ...] [stack:BYTES]
#   e.g. build_nanoda_variant.sh scratch/nanoda-let master scratch/bin/nanoda.master+71 merge:https://github.com/nealmcb/nanoda_lib#infer-let-local
set -euo pipefail
DIR=$1; REF=$2; OUT=$3; shift 3
[ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
[ -d "$DIR/.git" ] || git clone -q https://github.com/ammkrn/nanoda_lib "$DIR"
cd "$DIR"
git fetch -q origin
git reset -q --hard
git checkout -q --detach "origin/$REF" 2>/dev/null || git checkout -q --detach "$REF"
info="base $(git rev-parse --short=10 HEAD) ($REF)"
for x in "$@"; do
  case $x in
    merge:*) u=${x#merge:}; git fetch -q "${u%#*}" "${u#*#}"
             git -c user.name=build -c user.email=build@localhost merge -q --no-edit FETCH_HEAD
             info="$info; merged ${u#*#} at $(git rev-parse --short=10 FETCH_HEAD)";;
    patch:*) git apply "${x#patch:}"; info="$info; patch ${x#patch:}";;
    stack:*) sed -i "s/pub(crate) const STACK_SIZE: usize = [0-9_]*;/pub(crate) const STACK_SIZE: usize = ${x#stack:};/" src/lib.rs
             grep -q "STACK_SIZE: usize = ${x#stack:};" src/lib.rs || { echo "STACK_SIZE not set" >&2; exit 1; }
             info="$info; STACK_SIZE ${x#stack:}";;
    *) echo "unknown argument $x" >&2; exit 2;;
  esac
done
cargo build --release 2>&1 | tail -2
mkdir -p "$(dirname "$OUT")"
cp target/release/nanoda_bin "$OUT.new" && mv "$OUT.new" "$OUT"
echo "$info" | tee "$OUT.info"
