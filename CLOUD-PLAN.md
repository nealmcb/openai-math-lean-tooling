# Cloud plan: an independent run of the openai/math Lean measurements

Status: a pilot has run (2026-10-13, about $0.30); the full run has not started. Prices are
us-east-1 on-demand figures read from the AWS price list on 2026-10-11 and must be checked again
before ordering. Speed factors come from the pilot on one instance type.

## Why a second machine

The laptop (REPORT.md section 1b) has already built every module the Comparator configurations
need and accepted all 416 configurations, so the cloud is not needed for the main result. It adds
three things the laptop cannot give:

1. **Independent reproduction** on a stock Ubuntu image from a clean checkout, at the default
   `vm.max_map_count` of 65530, using only `tools/cloud_bootstrap.sh` and the versions in
   `MANIFEST.txt`.
2. **Clean timings.** The laptop is thermally limited and every timing came from a loaded run; the
   cloud gives dedicated cores and no pauses.
3. **Experiments that need repeated, quiet runs or a second toolchain**, such as the `-DMMAP=OFF`
   and `GLIBC_TUNABLES` comparisons.

## Pilot (results in `results/cloud-pilot/`)

One m7a.2xlarge (8 vCPU AMD EPYC 9R14, 32 GiB, Ubuntu 24.04, 120 GB gp3), about 30 minutes,
started from nothing by `tools/cloud_bootstrap.sh` (3 min 20 s: toolchain, Mathlib cache, landrun,
lean4export, comparator), then `tools/run_comparator_batch.py` on two configurations.

| | MatchingFPRAS | FourierLLogL |
|---|---|---|
| Modules built beyond the Mathlib cache | 416 | 157 |
| Compile speed-up over the laptop's first-build times | 3.7 | 4.8 |
| Build wall time on 8 vCPU | 604 s | 467 s |
| Check time, cloud / laptop | 151 s / 204 s | 151 s / 158 s |
| Check peak memory | 7.3 GiB | 7.2 GiB |

Both were accepted, with peak mappings near 54,000 at the default limit. Reading the numbers:

- Compiles are about four times faster than the laptop's times. That is an upper bound on the gain,
  because the laptop's times came from a loaded, thermally limited machine.
- The kernel check is single-threaded and is not much faster (1.0 to 1.4 times). With 80 hours of
  check work and a longest check of 10.9 hours on the laptop, the checks, not the compiles, set the
  length of the run.

## Sizing from the pilot

`tools/cloud_schedule_model.py` simulates the dependency graph of the 107,978 modules and 416
checks. With compiles 3.7 times faster:

| vCPU | check speed 1.0 | check speed 1.2 | check speed 1.4 |
|---|---|---|---|
| 16 | 16.0 h | 15.2 h | 14.6 h |
| 32 | 11.6 h | 9.8 h | 8.5 h |
| 64 | 11.6 h | 9.7 h | 8.4 h |

- 64 vCPU is no faster than 32, because the longest check (PlanarPacking) bounds the run: about
  9 h of the total, starting as soon as its modules are built.
- **Machine:** m7a.8xlarge (32 vCPU, 128 GiB), about $1.85 per hour on-demand (half of the verified
  $3.71 for the m7a.16xlarge). Memory: compiles reach 7 to 10 GiB for the heaviest modules and
  checks 6.5 GiB typically and 26 GiB at most, so 128 GiB allows 32 compile slots plus a few checks;
  limit the number of concurrent checks, not the compile slots.
- **Disk:** about 630 GB of generated `.setup.json` and C files without archiving, 80 to 105 GB of
  `.olean`, 25 GB of packages: provision 1.5 TB gp3 (about $2 for the run). Throughput of a full
  run is untested; raise gp3 throughput if the build stalls on I/O.
- **Spot:** not for this run. The long checks cannot resume, and an interruption would lose hours.

Cost: about 10 hours on-demand, $19 for the instance plus $2 for disk and a few dollars of
transfer and storage for results, so **$25 to $30**, against a budget alarm at $100 per month.

## Run plan

1. **Instance:** m7a.8xlarge in us-east-1, Ubuntu 24.04, 1.5 TB gp3, the existing
   `experiment-instance-role`, ssh from one address only, `instance-initiated-shutdown-behavior
   terminate`, and `shutdown -h +900` as a hard stop at 15 hours.
2. **Bootstrap:** `tools/cloud_bootstrap.sh` (idempotent; the repository is placed at
   `BASE`, by default the path the existing volume uses; the tools find it from their own location).
3. **Run:** `tools/pipeline.py` with enough workers for the checks, building everything in one batch
   under `tools/vmamon.py`; no archiving. Start the configurations with the longest predicted checks
   first (`results/check-cost-predictions.csv`).
4. **Teardown:** a watcher on the instance uploads `results/` and the logs to the private bucket and
   shuts the instance down when the run ends, as in the pilot, so the instance never outlives the
   work. Copy the results to the laptop from the bucket afterwards.
5. **Optional, on the same instance after the main run:** the `-DMMAP=OFF` and `GLIBC_TUNABLES`
   comparison on a fixed module subset (for example the `Progressions.Main` closure of 4,774 modules),
   at least three trials per variant, recording wall time, CPU time, peak memory and mappings; and
   repeated timings of the root import.

## Still to do before ordering

- `run.sh` that starts the pipeline with the cloud settings (workers, check concurrency) and the
  teardown watcher.
- Decide whether to make the repository relocatable (29 hard-coded occurrences of the base path in
  23 tool files); the bootstrap works around it by using the same path.
- A second, longer pilot at 32 vCPU for an hour (about $2) to check scaling beyond 8 vCPU and the
  disk throughput, before the full run.

## Risks and unknowns

- Scaling beyond 8 vCPU and the I/O of 32 concurrent compiles writing about 5 MB of `.setup.json`
  each are not measured.
- The compile speed-up factor is relative to loaded laptop times; the real wall time may be
  longer or shorter, which the model shows matters little because the longest check dominates.
- The longest checks (PlanarPacking 10.9 h, MUBSix 4.7 h on the laptop) must run on-demand and to
  completion.
- Lean's `-DMMAP=OFF` build and its interaction with the Mathlib cache have not been tried.
