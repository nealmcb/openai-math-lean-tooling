# Lake artifact cache for the openai/math Lean library (all modules, two commits)

A Lake artifact cache of the complete OAI build, stored as compressed per-module bundles (zstd,
about 20x smaller than the raw files) in a Cloudflare R2 bucket, which only needs to serve them as
ordinary static files over HTTPS. With it, `lake build` of any OAI result downloads the compiled
files of just the modules that result needs instead of compiling them. Nothing here is a
verification of the proofs; it only saves compile time, and Lake's 64-bit hashes are not
cryptographic.

Contents of the bucket `openai-math-lean` (scope `openai-math/lean-4.34.1`; Lean 4.34.1, Mathlib
`d13f23b7`, x86-64 Linux), for two openai/math commits:
- `r/openai-math/lean-4.34.1/REV.jsonl`: the mappings of one commit, one line per module: input
  hash, then the name of its bundle.
  - `7ef5c0cc5ca4b0e072b7a050fca09ab24bc6fa3a` (2026-10-26): 162,418 lines (162,417 modules plus
    the root `OAI`), 7.5 MB.
  - `fd4aeeb2ee4fc729c18d98444fed42fd0529eeeb` (2026-10-07): 122,459 lines, 5.6 MB.
- `a/openai-math/lean-4.34.1/HASH.art`: one bundle per distinct module build (zstd-compressed
  `.olean`, `.ilean`, `.c` and trace), 162,675 in all, about 5.1 GiB, 38 KB on average. The two
  commits share the bundles of every module whose inputs did not change. (The raw files of the
  laptop's build of 115,196 modules at `fd4aeeb2ee` are 93 GB.)

The `.olean` files embed the Lean version, so they load only with exactly Lean 4.34.1. The cache
covers only the OAI modules; Mathlib and the other dependencies come from their own caches via
`lake update`.

## Quick use

In a checkout of openai/math at commit `7ef5c0cc5` or `fd4aeeb2ee` with `lake update` done, put
this in
`~/.lake/config.toml` (once):

```
cache.defaultService = "oai"

[[cache.service]]
name = "oai"
kind = "s3"
artifactEndpoint = "https://pub-7e3c38d28090402696f4d21cb0c6f98c.r2.dev/a"
revisionEndpoint = "https://pub-7e3c38d28090402696f4d21cb0c6f98c.r2.dev/r"
```

Then, in the `lean` directory of the checkout:

```
export LAKE_ARTIFACT_CACHE=true
lake cache get --scope=openai-math/lean-4.34.1 --mappings-only   # once; the 5.6 MB list
lake build OAI.Some.Module                                       # downloads, does not compile
```

Editors that run `lake` (such as `lean4-mode` in Emacs) then use the cache too, if they start
with `LAKE_ARTIFACT_CACHE=true` in their environment.

## Worked example from a fresh directory, with timings

Starts from nothing: needs elan; takes about 5 minutes and a few GB for the dependencies and
Mathlib's own cache.

```
step() { echo; echo "== $(date +%T) $*"; }
export BASE=https://pub-7e3c38d28090402696f4d21cb0c6f98c.r2.dev
export PATH=$HOME/.elan/bin:$PATH

step "1. sparse clone of openai/math at the pinned commit (only what these two results need)"
mkdir -p /tmp/oai-cache-test && cd /tmp/oai-cache-test
time git clone -q --depth 1 --filter=blob:none --sparse --no-checkout https://github.com/openai/math
cd math
time git fetch -q --depth 1 origin fd4aeeb2ee4fc729c18d98444fed42fd0529eeeb
git checkout -q fd4aeeb2ee4fc729c18d98444fed42fd0529eeeb
git sparse-checkout set --no-cone /lean/lakefile.lean /lean/lake-manifest.json /lean/lean-toolchain /lean/patches/ /lean/OAI/Algebra/FormulaHitting/ /lean/OAI/Analysis/TriangularHilbert/
echo "OAI source files checked out: $(find lean/OAI -name '*.lean' | wc -l), size $(du -sh . | cut -f1)"
cd lean

step "2. lake update: clones the 42 dependency packages and unpacks Mathlib's own cache (the slow step, a few GB)"
time lake update > ../lake-update.log 2>&1
tail -2 ../lake-update.log; echo "packages: $(ls .lake/packages | wc -l)"

step "3. point Lake at the cache (config file, the address comes from \$BASE)"
cat > ../lake-cache.toml <<EOF
cache.defaultService = "oai"

[[cache.service]]
name = "oai"
kind = "s3"
artifactEndpoint = "$BASE/a"
revisionEndpoint = "$BASE/r"
EOF
export LAKE_CONFIG=$PWD/../lake-cache.toml LAKE_ARTIFACT_CACHE=true LAKE_CACHE_DIR=$PWD/../lake-cache-dir   # keeps this test's cache in one directory you can delete
lake cache services

step "4. lake cache get --mappings-only: downloads the list of everything the cache holds (5.6 MB)"
time lake cache get --scope=openai-math/lean-4.34.1 --mappings-only 2>&1 | grep -E "remote URL|error"
echo "mapping lines: $(cat $LAKE_CACHE_DIR/revisions/OAI/*.jsonl | wc -l) (one per module, plus a header line)"

step "5. lake build of the two results: restores the files from the cache instead of compiling"
time lake build OAI.Algebra.FormulaHitting.Hitting OAI.Analysis.TriangularHilbert.Main 2>&1 | tee ../lake-build.log | tail -2
echo "OAI modules compiled (0 means all came from the cache): $(grep -c 'Built OAI' ../lake-build.log)"
echo "OAI bundles downloaded from the cache: $(ls $LAKE_CACHE_DIR/artifacts | grep -c ltar), $(du -ch $LAKE_CACHE_DIR/artifacts/*.ltar | tail -1 | cut -f1) in all"
echo "whole cache directory (Lake also copies Mathlib's files into it): $(du -sh $LAKE_CACHE_DIR | cut -f1)"
echo "files now in the build directory: $(find .lake/build/lib/lean/OAI -type f | wc -l)"
step "done"
```

To use other results, add their directories to the `sparse-checkout set` line (or check out
everything) and name them in the `lake build` line; for the whole library build the module `OAI`.

Expected, measured on a 16-thread laptop: step 4 takes about 100 s (it parses 122,459 mapping
lines), step 5 about 50 s and compiles no OAI module (no "Built OAI..." lines), fetching 129 small
files on demand (2.8 MB). Without the cache the same build takes about 7.5 minutes. With
`LAKE_ARTIFACT_CACHE=true` Lake also copies every dependency's build outputs (Mathlib's, about 6.7
GB) into the cache directory, which accounts for part of the build time; delete
`/tmp/oai-cache-test` when you are done. `--mappings-only` needs the service in a config file
(`LAKE_CONFIG` or `~/.lake/config.toml`), not in environment variables; environment variables work
for a plain `lake cache get`, which downloads everything listed.

## On a machine with little disk

Building the whole library needs far more disk than most machines have (see section 6 of the
report). With the cache you never build or keep the whole library: check out only the
directories of the results you want, and Lake downloads and unpacks just their import closures.
- The cache is compressed, about 5.1 GiB for both commits, and only the bundles a build needs
  are downloaded (2.8 MB for the 129 modules above).
- With `LAKE_ARTIFACT_CACHE=true` Lake also copies each dependency's outputs (Mathlib's, about
  7 GB) into its local cache directory. With elan that directory is
  `~/.elan/toolchains/<toolchain>/lake/cache`; set `LAKE_CACHE_DIR` to put it on a larger disk.
  `du -sh` of it shows what `lake cache clean` would free (there is no dry run).
- By default an up-to-date module is taken from the cache without copying its outputs into
  `.lake/build`; only traces and hashes appear there. Set `LAKE_RESTORE_ARTIFACTS=true` for
  tools that read the `.olean` and `.c` files directly.
- Modules not in the cache are compiled as usual, and the `.olean` files of a closure must be
  uncompressed on disk while in use because Lean memory-maps them.
- If you do have to compile many modules on a small disk, `tools/archive_closure.py` and
  `tools/restore_ir_for.py` compress and restore the generated C files as a run goes along; with
  `--from-cache` the second one restores a config's OAI modules from the cache instead.

## How the cache was made (no rebuild needed)

On a machine with the complete build (here the cloud machine of the study, 32 vCPUs),
`LAKE_ARTIFACT_CACHE=true LAKE_CACHE_DIR=DIR lake build MODULES -o map.jsonl` on an up-to-date
workspace compiles nothing; Lake writes the mappings and one `.ltar` bundle per module into DIR.
Several such processes can share one cache directory.
1. `tools/lake_cache_convert.py WORKSPACE OUT --procs 8` splits the modules by area, runs the Lake
   processes concurrently and merges their mappings into `OUT/map-all.jsonl`. It converted all
   122,458 modules in 875 s (the groups took 594 s; the root module `OAI` followed). Timings per
   group: `results/lake-cache/timings.txt`.
2. `tools/lake_cache_upload.sh OUT BUCKET openai-math/lean-4.34.1
   fd4aeeb2ee4fc729c18d98444fed42fd0529eeeb` hardlinks the bundles as `HASH.art` and uploads them
   with rclone (64 transfers, 8 minutes for 4.3 GiB), the mappings last. Credentials were passed to
   the instance by `tools/push_r2_env.sh`.
3. The merged mapping is the file under `r/` in the bucket, listed above.

The `7ef5c0cc5` revision was made the same way by `tools/cloud_cache_update.sh` on a 32-vCPU spot
machine whose data volume held the `fd4aeeb2ee` build: it built the 1,540 modules no earlier run
had compiled (`lake build OAI`), converted all 162,418 in 2,249 s, and the upload sent the 40,216
new bundles (0.77 GiB) in 9.5 minutes, rclone skipping those already in the bucket. Logs:
`results/cache-7ef5c0cc5/`.
