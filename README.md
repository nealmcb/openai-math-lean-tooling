# openai-math-lean-tooling

*OpenAI Math: Lean? Tools & experience on a laptop - CPU-days, disk, mmap requirements*

Tooling, measurements and a report for building and checking the Lean library in
[openai/math](https://github.com/openai/math).

This is an independent, third-party project. It is not affiliated with or endorsed by OpenAI. It was
developed with assistance from Claude Code (Anthropic); every measurement in the report comes from a
recorded run of the code in this repository, with results under `results/`.

## What it answers

1. What does it take to start to verify the OpenAI Math formalizations in Lean?
2. How many memory mappings (`vm.max_map_count`) does Lean need to compile and check the openai/math
   library, and what drives the number?
3. Which of the repository's Comparator configurations check out, how long does each take, and what
   does a pass actually establish?
4. What would a different Lean kernel (here nanoda, in Rust) do for the same checks: how much faster
   or slower, how does it use extra cores and memory, and where does it fail?

The project is a reproducibility and resource-measurement exercise. It does not try to validate the
manuscripts' mathematics.

## If you want to check one result

Each of the 416 Comparator configurations in `ComparatorChallenges/` is a separate job with two Lean
files. The challenge file is small (median 2.6 KB) and states the theorem in Lean, usually using
only Mathlib's definitions (386 of the 416 import nothing else), with the proof left as `sorry`; the
one for `QuasiRiemannHypothesis` is 169 bytes. The solution file, in `OAI/`, supplies the proof and
may import thousands of OAI modules. Comparator builds the solution, exports its compiled
declarations, and has the Lean kernel re-check the solution's proof, confirm that the theorem
statement is identical to the challenge's, and confirm that only the permitted axioms are used.

A pass therefore shows that the Lean proof is valid for the Lean statement in the challenge file.
Whether that statement is a faithful formalization of the claim in a paper, or the paper is correct,
is a separate question that Comparator does not address.

Mathlib comes from the cache, so the cost you pay is the solution's own import closure (the OAI
modules it needs) plus the check. Measured here for the accepted configurations:

| Closure size (OAI modules) | Configs | Median closure | Compile CPU time, median (max) | Check time, median / p90 / max | Check memory, median (max) |
|---|---|---|---|---|---|
| up to 100 modules | 230 | 39 | 0.3 h (4 h) | 4 min / 10 min / 43 min | 6.4 GiB (20 GiB) |
| 101 to 500 | 112 | 212 | 1.1 h (52 h) | 4 min / 39 min / 2.0 h | 6.5 GiB (20 GiB) |
| 501 to 2,000 | 59 | 720 | 3.1 h (39 h) | 6 min / 26 min / 10.9 h | 6.9 GiB (13 GiB) |
| over 2,000 | 15 | 2925 | 8.2 h (60 h) | 15 min / 46 min / 4.7 h | 7.6 GiB (26 GiB) |
| all 416 accepted | 416 | 78 | | 4 min / 17 min / 10.9 h | 6.5 GiB (26 GiB) |

(`tools/cost_table.py` regenerates this table. Check times are on the laptop with Lean's kernel.)

- **Building scales with size, checking mostly does not.** The compile time of the closure grows
  with the number of modules, while the typical check takes about 4 minutes in every size class. A
  size class therefore bounds the build cost well and the check cost poorly: a small closure can
  hold an expensive proof. Look up the configuration itself in `results/cost-outliers.csv` (one row
  per configuration: check time, check memory, closure size, compile time) before starting.
- **Compile times** are wall-clock seconds under load on one thermally limited laptop, so they are
  upper bounds for isolated builds, and they divide across cores.
- **Memory:** a typical check peaked at about 6.4 GiB and the heaviest at 26 GiB; individual Lean
  compiles reached 7 to 10 GiB for the largest generated modules. Smaller machines were not tested.
- **Mapping limit:** every single-configuration build and check stayed under the Linux default
  `vm.max_map_count` of 65,530 (highest measured 58,559); see the findings below.
- **Why costs vary so much** is discussed in section 3d of [REPORT.md](REPORT.md): the expensive
  checks appear to be large generated certificates checked by kernel computation, not long
  structural proofs. That is a hypothesis from a few samples.

## A note on scale

The `OAI` library in [openai/math](https://github.com/openai/math) contains 122,458 AI-generated
Lean files and 26.1 million lines—eleven times the size of
[Mathlib](https://github.com/leanprover-community/mathlib4), the remarkably extensive,
community-built library covering much of modern undergraduate mathematics and substantial areas of
graduate-level and research mathematics. Mathlib took hundreds of contributors nearly a decade to
build. **For something called Lean, this is a lot to digest.** At 1,000 lines an hour, merely
reading all of OAI once would take 13 person-years of full-time work, never mind understanding it.
Machine-checkable proofs are valuable, but as
[Terence Tao](https://mathstodon.xyz/@tao/117395267721642920) and
[David Bessis](https://davidbessis.substack.com/p/the-fall-of-the-theorem-economy)
emphasize, mathematical progress also requires exposition, community building, and understanding—not
just more theorems.

These full-library costs matter mainly for independent reproduction, for maintainers, and for anyone
trying to assess the collection as a whole. Rebuilding and checking all of it took, on a thermally
limited laptop, 3.8 days of wall time (about 570 module-hours of compiling and 80 hours of checks),
150 to 200 GB of disk with careful archiving (about 700 GB without), up to 26 GiB of memory for a
single check, and a memory mapping budget that the Linux default of 65,530 only just covers for the
deepest modules. On one 32-vCPU cloud machine the same compiling, for every module of the library,
took 13.8 hours (section 3g of the report).

The scale problem should not be overstated for routine work. A mathematician using one result needs
only the transitive import closure of the modules involved, a small fraction of the library, and
neither rebuilds nor reads the other 26 million lines. Across the 416 Comparator configurations the
median closure is 77 modules (about 0.07% of the whole), 90% have at most 735 modules, and the
largest is 4,774. Small configurations (under 100 modules) took a median of about 2.5 minutes to
check here; a configuration with a closure of about 2,900 modules took under an hour to build and
about 9 minutes to check. Even a one-module configuration pays the memory-mapping cost of Mathlib
(about 54k of the 65,530 default in the checker), so that cost comes from Mathlib, not from the size
of `OAI`.

## Findings so far

Details, method and caveats are in [REPORT.md](REPORT.md). Versions pinned in
[MANIFEST.txt](MANIFEST.txt): openai/math `fd4aeeb2ee`, Lean 4.34.1, Mathlib `d13f23b7`, run on
Ubuntu 22.04.5 with the default limit of 65530.

- Lean maps one file per imported module, plus four more for modules built with the module system
  (Mathlib, Lean core). Peak mappings per process are about `40 + 5*M + O`, where M counts
  module-system modules and O ordinary modules in the import closure.
- Mathlib and Lean core already cost about 56k of the 65,530. The deepest non-root OAI modules are
  predicted at about 61k and were measured at 57 to 58.6k. The only module that exceeds the default
  is the aggregate `OAI.lean`, which needs 148,940 mappings (measured: it fails at 148,000 and
  succeeds at 150,000).
- At Mathlib's recent growth rate, the headroom under the Debian and Ubuntu default is roughly 0.6
  to 1.5 years (a straight-line extrapolation, section 3b of the report).
- Comparator accepted all 416 configurations (`results/cmp-all/configs.csv`) and rejects the
  negative controls in `controls/`. The slowest check took 10.9 hours of active time
  (`PlanarPacking`); 329 of 416 took under 10 minutes.
- The second kernel, nanoda, accepts 401 of the 416 configurations and takes a median of 0.21 of Lean's replay time on a paired sweep of 390 (about 5 times faster on 4 threads). It scales
  almost linearly with threads on large exports (`PlanarPacking`, 3.85 GB export, 672 s on 64 threads against 10.9 hours with Lean's kernel); the 18 configurations whose Lean-based check took
  over 2,000 s run 3.5 times faster end to end, 15 of them passing. It fails on 15 configurations (a stack overflow, or a memory blow-up past its 31-bit index limit) that Lean's kernel handles in
  seconds to minutes; two backtraces show the same non-terminating reduction, reported as
  [nanoda_lib issue 55](https://github.com/ammkrn/nanoda_lib/issues/55). Details and a minimal reproduction: section 3f of the report and `results/nanoda-repro/`.
- The Comparator solutions import 88% of the library's modules. The other 14,481 modules, which Lean's kernel checked only inside the build, were checked with nanoda: 76 of 77 batches pass
  (about 437,000 named declarations), one fails on a single declaration of the same kind (section 3h of the report).
- Skipping Lean's kernel check while compiling (`-D debug.skipKernelTC=true`) saves about 15% of the
  library's compile CPU time and 27% of its wall time (a sample of 26 modules).

An accepted configuration shows that the Lean solution proves the stated challenge statement using
only the permitted axioms. It does not show that the challenge statement matches the paper, or that
the paper is correct.

## If you want to reproduce everything

The whole library is a different scale of job from one configuration (see the note on scale above).
The estimates below are for the full run on the hardware used.

### Resource estimates (rough)

Full detail and the basis for each figure are in section 1a of [REPORT.md](REPORT.md). Treat these
as plus or minus 50%.

| Resource | Estimate |
|---|---|
| Wall-clock time, build every module and run Comparator on all 416 configurations | laptop (16 threads): 3.8 days; one 32-vCPU cloud machine: 13.8 hours of building, then the checks (the longest, `PlanarPacking`, 9 to 11 hours with Lean's kernel, 11 minutes with nanoda on 64 threads) |
| Disk | about 150 to 200 GB working set with the pipeline's archiving of generated build files; about 700 GB if they are kept (497 GB of it transient `.setup.json` files); a finished library build kept for later use is 116 GB |
| CPU time | about 410 CPU-hours with Lean's kernel (compiling 330, Comparator checks 80); about 325 with nanoda replacing Lean's kernel for the 416 configurations, about 365 if it also covers the modules no solution imports (section 1a of the report; laptop-equivalent, plus or minus 30%) |
| Memory | builds about 20 to 30 GiB at full speed; checks typically 6.5 GiB, up to 26 GiB; 64 GiB recommended |
| `vm.max_map_count` | the default 65,530 for everything except the root `OAI.lean`, which needs at least 150,000 |

Hardware used: Framework Laptop 13, Core i5-1340P (4 performance cores with hyper-threading plus 8
efficiency cores, 16 threads, thermally limited), 60 GiB RAM, 39 GiB swap, 2 TB NVMe, Ubuntu
22.04.5, kernel 6.8.

## Layout

| Path | Contents |
|---|---|
| `tools/vmamon.py` | Runs a command and records per-process mapping counts, memory, CPU and an explicit failure classification |
| `tools/predict_vmas.py`, `closure_sizes.py`, `import_memory_probe.py`, `importclosure.py`, `external_reach.py` | Import-graph analysis and mapping prediction for every module |
| `tools/pipeline.py`, `run_comparator_batch.py` | Batched builds plus parallel Comparator checks, resumable, with per-batch archiving of generated build files |
| `tools/root_build.py`, `root_import_trial.py` | Build the modules only `OAI.lean` needs, in chunks, and import the whole library at a chosen mapping limit |
| `tools/cloud_bootstrap.sh`, `cloud_run.py`, `priority_build.py`, `cloud_finish_build.py`, `cloud_status.sh`, `cloud_schedule_model.py`, `make_throttled_sysroot.sh` | Cloud run: install, priority-ordered parallel builds without compiling a module twice, status, and the schedule model |
| `tools/nanoda_pilot.py`, `nanoda_scaling.py`, `nanoda_stack_test.py`, `nanoda_thread_model.py`, `nanoda_cost_proxy.py`, `kernel_pair_sweep.py`, `kernel_replay_time.lean`, `skip_kernel_test.py`, `skip_kernel_sample.py`, `export_vs_check.py`, `profile_from_builds.py`, `tools/patches/` | Second-kernel study: nanoda against Lean's kernel, thread scaling, per-declaration times, the skip-kernel build option, and the local patches (a Comparator option to skip Lean's replay; nanoda with a configurable stack and per-declaration times) |
| `tools/cloud_long_nanoda.sh`, `cloud_long_launch.sh`, `uncovered_check.py`, `list_module_decls.lean`, `solution_coverage.py`, `isolate_decl.py`, `cpu_hours_estimate.py` | The long configurations and the modules no solution imports checked with nanoda on a cloud machine; which modules the solutions reach; one declaration exported and checked alone; the CPU-hours estimate |
| `tools/pause.sh`, `resume.sh`, `idle_guard.py` | Instant pause and resume of a run; resume when the GNOME screen blanks |
| `tools/parallelism_profile.py`, `export_results.py`, `export_module_times.py`, `check_time_factors.py`, `cost_outliers.py`, `cost_table.py`, `overnight_status.py`, `mdwrap.py` | Build-parallelism profile, per-config CSV, check-cost factors and outliers, status summary |
| `controls/` | Negative controls for Comparator (sorry, extra axiom, `native_decide`, mismatched statement) |
| `results/` | Per-run summaries; `results/cmp-all/configs.csv` (one row per config; read the build-time caveats in REPORT.md section 3c); `results/module-times.csv.gz` (one row per module with its compile time); prediction and closure data |
| `REPORT.md`, `MANIFEST.txt` | Findings, exact versions |

## Reproducing

The scripts currently assume the checkout lives at `/home/srv/s/math/openai-math` (the `base`
variable near the top of each script). Change it, or use that path, until this is made configurable.

Needs: [elan](https://github.com/leanprover/elan), Python 3, `tmux`, `systemd --user`, Linux with
Landlock (kernel 5.13 or later), Go 1.24 or later (for landrun), and a Rust toolchain only if you
want the optional second kernel (nanoda).

1. Clone openai/math into `src/` and check out the commit in `MANIFEST.txt`. In `src/lean`, run
   `lake update` (it applies the repository's compatibility patches) and `lake exe cache get`.
2. Build the checking tools into `ext/` at the commits listed in `MANIFEST.txt`: comparator,
   lean4export, landrun, and optionally nanoda_lib. Set the `lean-toolchain` of comparator and
   lean4export to the same version as the project (otherwise lean4export fails with "incompatible
   header"), and put the binaries on `PATH`.
3. Measure one build:
   `python3 tools/vmamon.py --out results/example -- lake build OAI.Combinatorics.Progressions.Main`
   (run it from `src/lean`).
4. Predict mapping counts for every module:
   `python3 tools/predict_vmas.py src/lean <toolchain>/src/lean out.jsonl`. This took several hours
   on a loaded laptop.
5. Run Comparator on all configurations: `python3 tools/pipeline.py --workers 3`. It resumes from
   `results/cmp-all/all.jsonl`, and `tools/export_results.py` writes the per-config table.

`tools/with_maxmap.sh` sets `vm.max_map_count` for one command and restores it; it needs a sudoers
rule limited to that one `sysctl` call. The generated build files (almost all of them per-module
`.setup.json` import lists) reach about 5 MB per module, so a full run needs several hundred GB
unless the pipeline's archiving is used.

## Status and limits

Comparator has accepted all 416 configurations, the whole library (every `OAI` module, including
the root `import OAI`) has been built and the root import measured (section 3e of the report), and
the second-kernel study (nanoda) covers the paired sweep, the long configurations and the modules no
solution imports (sections 3f and 3h; 15 configurations and one further declaration fail in nanoda,
with the cause still open, see [nanoda_lib issue 55](https://github.com/ammkrn/nanoda_lib/issues/55)). Not done: the
`-DMMAP=OFF` comparison, repeated trials for variance, and per-declaration Lean-kernel times to
compare with nanoda's. Sampled mapping peaks are lower bounds. The laptop timings come from one
thermally limited machine while other work was running, and some include periods when the run was
paused (the tables use active time); the cloud timings come from one instance type, and the CPU-hour
totals are rough estimates.

## License

MIT, see [LICENSE](LICENSE).
