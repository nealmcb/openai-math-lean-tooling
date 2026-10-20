#!/bin/bash
# archive_ir.sh NAME SUBDIR...: compress generated C (lake build/ir/<SUBDIR>) into archive/NAME.tar.zst, verify, then remove the originals.
# Purpose: free disk without discarding anything. Restore with:  tar --zstd -xf archive/NAME.tar.zst -C src/lean/.lake/build
# Note: Lake treats the C file as a tracked output; if a module whose C was archived is rebuilt via `lake build`, Lake regenerates it (seconds per module), so restore first to avoid that.
set -e
base=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd); b=$base/src/lean/.lake/build; name=$1; shift
mkdir -p $base/archive
cd $b
before=$(du -sk "$@" 2>/dev/null | awk '{s+=$1} END{print s}')
nice -n 10 ionice -c3 tar -cf - "$@" | zstd -T4 -3 -q -o $base/archive/$name.tar.zst
zstd -tq $base/archive/$name.tar.zst
n=$(tar --zstd -tf $base/archive/$name.tar.zst | grep -c '\.c$' || true)
echo "$name: $(( before/1024 )) MB -> $(( $(stat -c %s $base/archive/$name.tar.zst)/1048576 )) MB, $n .c entries verified readable"
find "$@" -type f -delete
