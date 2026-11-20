# Lake artifact cache for the OpenAI Yang-Mills Lean submission

The compiled files of the OpenAI Yang-Mills submission (`yang-mills-group/YM` at
`55ba9fc36293b3f4d52c6b1f813169a0be76ee98`, package `submissions/openai-20261028/submission`,
Lean 4.32.0, Mathlib `81a5d257c8e4`, x86-64 Linux), as a Lake artifact cache. Its build stage
(`lake build WilsonReference WilsonConstruction`) took 1 h 31 min on 32 vCPUs; with the cache it
takes about 1.5 minutes and compiles no module. It only saves compile time: it is not a
verification, and Lake's 64-bit hashes are not cryptographic. The nanoda check of the same
submission is in `../RUNS.md`.

Contents of the bucket `openai-math-lean` (the same bucket as the openai/math cache,
`../../lake-cache-test/README.md`), scope `yang-mills-openai-20261028/lean-4.32.0`:
- `r/yang-mills-openai-20261028/lean-4.32.0/55ba9fc36293b3f4d52c6b1f813169a0be76ee98.jsonl`: the
  mapping, 9,471 lines (9,470 modules plus a header), 420 KB. Same file as `map-all.jsonl` here.
- `a/yang-mills-openai-20261028/lean-4.32.0/HASH.art`: 9,470 bundles, about 400 MiB.

Mathlib and the other dependencies come from their own caches (`lake exe cache get`).

## Use

Download every bundle before building, and check them. The bucket's public `r2.dev` address
rate-limits bulk downloads (Cloudflare "error code: 1015") and refuses connections. Lake then keeps
the error response or an empty file as if it were the bundle, skips it on later runs, fails to
unpack it ("bad .ltar file") and compiles that module itself. The locally compiled module need not
be byte-identical to the cached one (2026-11-13: `Panes` was not), and then the cache keys of
everything that imports it change, and thousands of modules get compiled (4,452 in one test). Repeating the download until it
succeeds and deleting every file that is not a bundle (bundles start with the bytes `LTR3`) avoids
that:

```
git clone https://github.com/yang-mills-group/YM && cd YM
git checkout 55ba9fc36293b3f4d52c6b1f813169a0be76ee98 && cd submissions/openai-20261028/submission
lake exe cache get
cat > ../lake-cache.toml <<'EOF'
cache.defaultService = "oai"

[[cache.service]]
name = "oai"
kind = "s3"
artifactEndpoint = "https://pub-7e3c38d28090402696f4d21cb0c6f98c.r2.dev/a"
revisionEndpoint = "https://pub-7e3c38d28090402696f4d21cb0c6f98c.r2.dev/r"
EOF
export LAKE_CONFIG=$PWD/../lake-cache.toml LAKE_ARTIFACT_CACHE=true LAKE_CACHE_DIR=$PWD/../lake-cache-dir
for attempt in $(seq 20); do
  lake cache get --scope=yang-mills-openai-20261028/lean-4.32.0 > /dev/null 2>&1; rc=$?
  bad=0; for f in "$LAKE_CACHE_DIR"/artifacts/*.ltar; do [ "$(head -c 4 "$f")" = LTR3 ] || { rm -f "$f"; bad=$((bad+1)); }; done
  echo "attempt $attempt: exit $rc, invalid files deleted: $bad"; [ $rc = 0 ] && [ $bad = 0 ] && break; sleep 10
done
lake build WilsonReference WilsonConstruction 2>&1 | tee ../build.log | tail -2
echo "modules compiled: $(grep -c -E '\[[0-9]+/[0-9]+\] Built ' ../build.log) (0 means everything came from the cache)"
```

Run this on a fresh checkout. If a build has already compiled modules, delete its `.lake/build`
before trying again, or the locally compiled files keep changing the keys. Compiling Lean code can
run arbitrary code; a module the cache misses is compiled on your machine, so treat the
submission as untrusted code.

## Test

`tools/test_lake_cache_project.sh` does the steps above from an empty directory. Run on an
isolated spot instance (no credentials, metadata service off) on 2026-11-13 against this mapping:
the download took 16 attempts (the early ones each deleted about 1,000 invalid files), then
`lake build WilsonReference WilsonConstruction` exited 0 in 85 s with 0 modules compiled. Logs of
that run and the earlier failing ones: `cache-test-runs-20261113.tgz` (`test.out` is the passing
run; `test.out.no-retry` and `test.out.retry-no-validation` the two before it).
`cache-test.out` and `cache-test-build-logs.tgz` are the first test (83 modules compiled);
`fresh-root-miss-traces.tgz` holds the traces of its 9 root misses, which led to the diagnosis
(`tools/lake_cache_misses.py`, `tools/compare_lake_traces.py`).

## How it was made

On the machine that ran the 1 h 31 min build, `tools/lake_cache_project.sh` ran
`LAKE_ARTIFACT_CACHE=true lake build WilsonReference WilsonConstruction -o map-all.jsonl`, which
compiled nothing (log: `convert.log`). The bundles were copied to the laptop and uploaded from
there with `tools/lake_cache_upload.sh`, so that no credentials ever reached the machine that
compiled the untrusted code.
