#!/bin/bash
# with_oai_cache: run a command in src/lean with Lake pointed at the published OAI Lake cache (results/lake-cache-test/README.md).
#
# Purpose: build configurations of a newer openai/math commit on the laptop, taking every module whose Lake hash is unchanged since the cache's
# commit (fd4aeeb2ee) from the cache and compiling only the rest. Lake's `cache get` backtracks up to 100 commits to find the cache's mappings,
# so `with_oai_cache.sh lake cache get --scope=openai-math/lean-4.34.1 --mappings-only` works from a later commit too (once per cache dir).
# The config file and the cache directory live in DIR (default scratch/oai-lake-cache under the checkout), which can be deleted afterwards.
# Usage: [DIR=...] with_oai_cache.sh COMMAND [ARGS...]     e.g.  with_oai_cache.sh lake build OAI.Some.Module
HERE=$(dirname "$(readlink -f "$0")")
BASE=${CHECKOUT:-$(dirname "$HERE")}
DIR=${DIR:-$BASE/scratch/oai-lake-cache}
URL=https://pub-7e3c38d28090402696f4d21cb0c6f98c.r2.dev
mkdir -p "$DIR/cache"
[ -f "$DIR/lake-cache.toml" ] || printf 'cache.defaultService = "oai"\n\n[[cache.service]]\nname = "oai"\nkind = "s3"\nartifactEndpoint = "%s/a"\nrevisionEndpoint = "%s/r"\n' "$URL" "$URL" > "$DIR/lake-cache.toml"
# LAKE_RESTORE_ARTIFACTS: copy the cached .olean files into .lake/build, since Comparator's export reads them there and its own `lake env`
# runs without this cache configuration
export LAKE_CONFIG=$DIR/lake-cache.toml LAKE_ARTIFACT_CACHE=true LAKE_CACHE_DIR=$DIR/cache LAKE_RESTORE_ARTIFACTS=true PATH=$HOME/.elan/bin:$PATH
cd "$BASE/src/lean" || exit 1
exec "$@"
