#!/bin/bash
# cloud_bootstrap.sh: prepare a fresh Ubuntu 24.04 machine to build openai/math and run Comparator checks, at the versions in MANIFEST.txt.
#
# Purpose: the laptop run used a hand-built tool chain; this reproduces it from nothing so a cloud machine can do the same work. It
# installs elan and Lean 4.34.1, Go (for landrun), clones openai/math at the pinned commit into $BASE/src, fetches the Mathlib cache,
# builds landrun, lean4export and comparator at the pinned commits (with their lean-toolchain set to 4.34.1, otherwise lean4export fails
# with "incompatible header"), and checks that the tools start. Idempotent: each step is skipped if its result exists. The scripts in
# tools/ find the checkout from their own location, so BASE can be any directory (the default is where the
# existing cloud volume keeps it).
# Needs: git curl python3 build-essential (apt) and sudo for creating $BASE. Run as the normal user; takes about 10 minutes plus the cache.
# Options: --no-cache skips the Mathlib cache download; --nanoda also builds the second kernel (Rust, nanoda_lib at the pinned commit) into
# ext/bin/nanoda_bin; --aws-cli installs the AWS CLI v2 (to upload results from an instance role).
# Usage: cloud_bootstrap.sh [--no-cache] [--nanoda] [--aws-cli]      Log lines carry a UTC time stamp and the step name, for timing the set-up.
set -euo pipefail
BASE=${BASE:-/home/srv/s/math/openai-math}
GO_VERSION=${GO_VERSION:-1.24.7}
OAI_REV=fd4aeeb2ee4fc729c18d98444fed42fd0529eeeb
COMPARATOR_REV=d03acab154d269c06e60e4de7e4cc85deebff94b
LEAN4EXPORT_REV=076e8e57707e813375e8f9da8bf989799ace9680
LANDRUN_REV=811cfff51ceaf3d9843708aa6d22e9b84ccac8b4
NANODA_REV=3a2407216ee84a75f9e1aead6803d0578be06ae7
LEAN=leanprover/lean4:v4.34.1
step() { echo "$(date -u +%FT%TZ) bootstrap: $*"; }

step "directory $BASE"
if [ ! -d "$BASE" ]; then sudo mkdir -p "$BASE" && sudo chown "$USER" "$BASE"; fi
mkdir -p "$BASE"/{ext/bin,results,logs,scratch}

step "elan and Lean"
if [ ! -x "$HOME/.elan/bin/elan" ]; then curl -sSf https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh -s -- -y --default-toolchain none; fi
export PATH="$HOME/.elan/bin:$PATH"
elan toolchain install "$LEAN" >/dev/null

step "go $GO_VERSION"
if [ ! -x "$BASE/ext/go-toolchain/go/bin/go" ]; then
  mkdir -p "$BASE/ext/go-toolchain" && curl -sSfL "https://go.dev/dl/go$GO_VERSION.linux-amd64.tar.gz" | tar -C "$BASE/ext/go-toolchain" -xzf -
fi
export PATH="$BASE/ext/go-toolchain/go/bin:$PATH"

step "openai/math at $OAI_REV"
if [ ! -d "$BASE/src/.git" ]; then git clone -q https://github.com/openai/math "$BASE/src"; fi
git -C "$BASE/src" checkout -q "$OAI_REV"
cd "$BASE/src/lean"
step "lake update (applies the compatibility patches)"
if [ ! -d .lake/packages/mathlib ]; then lake update; fi
case " $* " in *" --no-cache "*) ;; *) step "lake exe cache get"; lake exe cache get >"$BASE/logs/cache-get.log" 2>&1 || { tail -5 "$BASE/logs/cache-get.log"; exit 1; } ;; esac

clone() {  # dir url rev
  if [ ! -d "$BASE/ext/$1/.git" ]; then git clone -q "$2" "$BASE/ext/$1"; fi
  git -C "$BASE/ext/$1" checkout -q "$3"
}
step "landrun"
clone landrun https://github.com/Zouuup/landrun "$LANDRUN_REV"
if [ ! -x "$BASE/ext/bin/landrun" ]; then (cd "$BASE/ext/landrun" && go build -o "$BASE/ext/bin/landrun" ./cmd/landrun); fi

step "lean4export"
clone lean4export https://github.com/leanprover/lean4export "$LEAN4EXPORT_REV"
echo "$LEAN" > "$BASE/ext/lean4export/lean-toolchain"
(cd "$BASE/ext/lean4export" && lake build >"$BASE/logs/lean4export-build.log" 2>&1)

step "comparator"
clone comparator https://github.com/leanprover/comparator "$COMPARATOR_REV"
echo "$LEAN" > "$BASE/ext/comparator/lean-toolchain"
(cd "$BASE/ext/comparator" && lake build >"$BASE/logs/comparator-build.log" 2>&1)

case " $* " in *" --nanoda "*)
  step "nanoda"
  if [ ! -x "$HOME/.cargo/bin/cargo" ]; then curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal >/dev/null 2>&1; fi
  . "$HOME/.cargo/env"
  clone nanoda_lib https://github.com/ammkrn/nanoda_lib "$NANODA_REV"
  if [ ! -x "$BASE/ext/bin/nanoda_bin" ]; then (cd "$BASE/ext/nanoda_lib" && cargo build --release >"$BASE/logs/nanoda-build.log" 2>&1 && cp target/release/nanoda_bin "$BASE/ext/bin/nanoda_bin"); fi ;;
esac
case " $* " in *" --aws-cli "*)
  step "aws cli"
  if ! command -v aws >/dev/null; then (cd "$(mktemp -d)" && curl -sSfL https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o a.zip && unzip -q a.zip && sudo ./aws/install >/dev/null); fi ;;
esac

step "check"
"$BASE/ext/bin/landrun" --help >/dev/null 2>&1 && echo "landrun ok"
ls "$BASE/ext/lean4export/.lake/build/bin/lean4export" "$BASE/ext/comparator/.lake/build/bin/comparator"
step "done"
