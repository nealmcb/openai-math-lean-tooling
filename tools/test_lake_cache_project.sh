#!/bin/bash
# test_lake_cache_project: from nothing, check that a published Lake cache lets a project build without compiling any of its modules.
#
# Purpose: before telling anyone a cache works, test it the way a user would (2026-11-12, for the Yang-Mills cache made with
# tools/lake_cache_project.sh). Every run starts in a new, empty directory WORK/run-<UTC time>: a run that was interrupted (a spot
# reclaim) must not be resumed, since Lake would reuse whatever it had compiled before the interruption, and one locally compiled module
# changes the cache keys of everything that imports it (2026-11-13: an interrupted first run compiled modules that the cache did hold,
# and the later runs inherited them). Steps: clone REPO at REV and enter PROJECT_SUBDIR; get the dependencies' outputs from their own
# caches (`lake exe cache get` when the project depends on Mathlib); point Lake at our cache service through a config file in the run
# directory (not ~/.lake); download the mappings and every bundle they name with `lake cache get --scope=SCOPE`, before building, so
# the build fetches nothing; run `lake build TARGETS`; count the modules it compiled. 0 means the cache covers the build. All output
# goes to files in the run directory (steps.log, cache-get.log, build.log), never overwritten. Untrusted projects: run it only on an
# isolated machine (tools/cloud_spot_scratch_launch.sh), since a module the cache misses would be compiled locally.
# Usage: [MAPPINGS=FILE] test_lake_cache_project.sh WORK REPO_URL REV PROJECT_SUBDIR SCOPE TARGET...   (prints the run directory first)
WORK=$(readlink -m "${1:?work dir}"); REPO=${2:?repo url}; REV=${3:?rev}; SUB=${4:?project subdir}; SCOPE=${5:?scope}; shift 5
URL=https://pub-7e3c38d28090402696f4d21cb0c6f98c.r2.dev
RUN=$WORK/run-$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$RUN" && cd "$RUN" || exit 1
echo "run directory $RUN"
export PATH=$HOME/.elan/bin:$PATH
step() { echo "== $(date -u +%T) $*" | tee -a "$RUN/steps.log"; }
step "clone $REPO at $REV"
git clone -q "$REPO" src && git -C src checkout -q "$REV" || exit 1
cd "src/$SUB" || exit 1
printf 'cache.defaultService = "oai"\n\n[[cache.service]]\nname = "oai"\nkind = "s3"\nartifactEndpoint = "%s/a"\nrevisionEndpoint = "%s/r"\n' "$URL" "$URL" > "$RUN/lake-cache.toml"
export LAKE_CONFIG=$RUN/lake-cache.toml LAKE_ARTIFACT_CACHE=true LAKE_CACHE_DIR=$RUN/lake-cache-dir
if grep -q mathlib lake-manifest.json; then step "dependencies: lake exe cache get"; lake exe cache get >> "$RUN/steps.log" 2>&1 || { step "lake exe cache get failed"; exit 1; }; fi
# MAPPINGS=FILE tests a mapping before it is published: the bundles come from the bucket, the mapping from the local file
step "our cache: lake cache get ${MAPPINGS:+$MAPPINGS }--scope=$SCOPE (mappings and every bundle they name)"
# The bucket's r2.dev URL refuses many of the connections of a bulk download (2026-11-13: 7,808 of 9,470 bundles failed with "Couldn't
# connect to server"); `lake cache get` skips bundles it already has, so repeat it until it succeeds, up to RETRIES times
# Worse, when the URL rate-limits a download (Cloudflare "error code: 1015") or the connection fails, Lake keeps the error response or
# an empty file as the bundle, later runs skip it as already present, and the build compiles the module instead ("bad .ltar file").
# So after each attempt delete every bundle that is not an LTR3 archive, and stop only when the download succeeded with none left.
for attempt in $(seq "${RETRIES:-20}"); do
  lake cache get ${MAPPINGS:+"$MAPPINGS"} --scope="$SCOPE" > "$RUN/cache-get.$attempt.log" 2>&1; rc=$?
  bad=0; for f in "$RUN"/lake-cache-dir/artifacts/*.ltar; do [ "$(head -c 4 "$f")" = LTR3 ] || { rm -f "$f"; bad=$((bad+1)); }; done
  step "lake cache get attempt $attempt: exit $rc; failed downloads: $(grep -c 'failed to download' "$RUN/cache-get.$attempt.log"); invalid bundles deleted: $bad; valid bundles: $(ls "$RUN/lake-cache-dir/artifacts" | grep -c ltar)"
  [ $rc = 0 ] && [ $bad = 0 ] && break; rc=1; sleep 10
done
[ $rc = 0 ] || exit 1
step "lake build $*"
lake build "$@" > "$RUN/build.log" 2>&1; rc=$?
step "lake build exit $rc; modules compiled: $(grep -c -E '\[[0-9]+/[0-9]+\] Built ' "$RUN/build.log") (should be 0)"
grep -E '\[[0-9]+/[0-9]+\] Built ' "$RUN/build.log" | head -5 | tee -a "$RUN/steps.log"
exit $rc
