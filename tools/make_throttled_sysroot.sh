#!/bin/bash
# make_throttled_sysroot.sh [BASE]: create BASE/ext/sysroot-throttled, a copy of the Lean 4.34.1 toolchain whose `lean` waits for a free slot.
# Purpose: Lake starts every compile whose dependencies are done, with no limit, so a wide build oversubscribes the CPUs (load 60 to 130 on 32
# vCPUs seen on the cloud machine) and every timing taken beside it is noisy. This sysroot caps the number of concurrent compiles ACROSS
# all Lake processes: `bin/lean` takes one of LEAN_SLOTS flock(2) locks (files in ./slots) before exec'ing the real lean, and the lock lives as
# long as that lean process. Use it as `LEAN_SYSROOT=BASE/ext/sysroot-throttled LEAN_SLOTS=N BASE/ext/sysroot-throttled/bin/lake build ...`.
# The laptop's copy (same layout) was made by hand; this builds the same thing for any host. Idempotent.
set -euo pipefail
BASE=${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}; T=$(ls -d "$HOME"/.elan/toolchains/leanprover--lean4---v4.34.1); S=$BASE/ext/sysroot-throttled
mkdir -p "$S/bin" "$S/slots"
for d in include lib share src LICENSE LICENSES; do [ -e "$T/$d" ] && ln -sfn "$T/$d" "$S/$d"; done
for f in "$T"/bin/*; do n=$(basename "$f"); case $n in lean|lake) ;; *) ln -sfn "$f" "$S/bin/$n";; esac; done
cp -f "$T/bin/lake" "$S/bin/lake"
cat > "$S/bin/lean" <<EOF
#!/bin/bash
# lean_throttle: run the real Lean only when one of N slot locks is free, to cap concurrent compiles (Lake ignores CPU affinity).
REAL=$T/bin/lean
N=\${LEAN_SLOTS:-10}
[ "\${1:-}" = "--githash" ] || [ "\${1:-}" = "--version" ] || [ "\${1:-}" = "--print-prefix" ] || [ "\${1:-}" = "--print-libdir" ] && exec "\$REAL" "\$@"
D="\$(dirname "\$(readlink -f "\$0")")/../slots"
while true; do
  for i in \$(seq 1 \$N); do
    exec {fd}>"\$D/slot.\$i"
    if flock -n \$fd; then exec "\$REAL" "\$@"; fi
    exec {fd}>&-
  done
  sleep 0.4
done
EOF
chmod +x "$S/bin/lean"; echo "made $S"
