# Report: can the default Linux memory mapping limit verify OpenAI/math Lean?

Status as of 2026-10-15 (a local workstation plus about $85 of cloud spend; the Comparator run, the root build, the full cloud build, the paired kernel
sweep and the nanoda checks are complete; the cause of the nanoda failures is open, see nanoda_lib issue 55). Repo pinned at openai/math commit fd4aeeb2ee4fc729c18d98444fed42fd0529eeeb, Lean
v4.34.1, Mathlib d13f23b723b8a846827a245b89c10fc7d3f11612. Raw data is under results/.

## 1. Bottom line

- On Ubuntu 22.04.5 (hardware-enablement kernel 6.8, `vm.max_map_count` = 65530) every build and Comparator check succeeded at the default
  limit: all 107,978 modules in the Comparator solution closure, and all the other modules of `OAI.lean`'s closure. The highest sampled
  single-process count in any non-root build was 58,559 (89% of the limit).
- The one module that fails at 65530 is the root `OAI.lean`: with every other module built it fails at the default limit with
  `failed to read file ...olean` after 13 s, fails at 148,000 and succeeds at 150,000 and above. Its peak is about 148,940 mappings in one
  process (143k to 149k predicted, section 3a; measured, section 3e).
- Comparator accepted all 416 configurations and rejected none. Four deliberately wrong solutions (a `sorry`, an extra axiom, `native_decide`,
  a mismatched statement) were all rejected. Active check time per configuration: median 266 s, 90th percentile 1,036 s, maximum 39,131 s
  (10.9 hours, `PlanarPacking`); 80 hours in all, 329 checks under 10 minutes and 12 over an hour. What an acceptance does and does not
  establish is in section 5. Nothing in this report validates the manuscripts' mathematics.
- The second kernel, nanoda, accepts 401 of the 416 configurations. On a paired sweep of 390 of them it takes a median of 0.21 of Lean's replay time (about 5 times
  faster, 4 threads against 1), and it scales with threads on large exports (`PlanarPacking`: 672 s on 64 threads against 10.9 hours of Lean's check). The 15
  it does not accept are all accepted by Lean's kernel in seconds to minutes; nanoda aborts on them with a stack overflow or a runaway that exhausts its 2^31-entry index
  space. Two backtraces show the same non-terminating `whnf` and `try_reduce_nat` alternation, reported as
  [nanoda_lib issue 55](https://github.com/ammkrn/nanoda_lib/issues/55) (section 3f).
- The Comparator solutions import only 88% of the library's modules. The other 14,481 modules were checked with nanoda in 77 batches: 76 pass (about 437,000 named
  declarations), one fails on a single declaration of the same kind (section 3h).
- Rough CPU cost of the whole job: about 410 CPU-hours with Lean's kernel (compiling 330, Comparator checks 80), about 325 with nanoda replacing Lean's kernel on the
  416 configurations, and about 365 if nanoda also covers the modules no solution imports (section 1a).
- The whole library (all 122,458 `OAI` modules, the root included) built on one 32-vCPU cloud machine in 13.8 hours, about 4.7 times the
  laptop's throughput (section 3g).

## 1a. Resources the full run took

Measured on the laptop (Comparator run and root build) and on one cloud machine (section 3g). The laptop numbers include other work running
at the same time and periods when the run was paused by hand; the check and compile figures are active times.

| Resource | Measured | Basis |
|---|---|---|
| Wall-clock time, laptop | 3.8 days for the Comparator run (all 416 configurations and the 107,978 modules they need), plus about 9 hours for the 6,460 modules only `OAI.lean` needs | first check started 2026-10-10 00:13 UTC, last finished 2026-10-13 about 21:00 UTC |
| Compiling | about 567 module-hours of first-build time (wall seconds under load, 79,171 modules timed) | `results/module-times.csv.gz`; median module 13 s, 90th percentile 36 s, maximum 4,968 s |
| Comparator checks (416) | 80.1 hours of active time; median 266 s, maximum 39,131 s | `results/cmp-all/configs.csv` |
| Disk, working set | about 150 to 200 GB with the pipeline's archiving of generated build files; 116 GB for a finished full-library build kept for later use | `.olean` and related outputs about 0.66 MB per module (68 GB `lib`), 31 GB of compressed archives of the generated build files |
| Disk, if the generated build files are kept | about 600 to 700 GB | 497 GB of `.setup.json` import lists on the cloud build (5.8 MB per module, 99.5% of the generated files; the `.c` files are about 30 KB per module); they compress to about 4% |
| Memory, build | 20 to 30 GiB of real memory at full speed on the laptop; one Lean process up to 10.5 GiB | lowest available memory seen during three big builds: 17 to 25 GiB of 60 |
| Memory, checks | median 6.5 GiB, 90th percentile 7.2, maximum 26.1 GiB (`MUBSix`) | 401 checks with a valid monitor |
| Memory, recommended | 64 GiB | tested on 60 GiB with 39 GiB of swap; the run used up to 18 GiB of swap |
| Mapping limit | the default 65,530 for everything except the root `OAI.lean`, which needs at least 150,000 | sections 3a and 3e |

**CPU-hours for the whole job (rough estimate, `tools/cpu_hours_estimate.py`, `results/cpu-hours-estimate.json`).** Both pipelines build every module once; they differ in
who checks the declarations. These are laptop-equivalent CPU hours (the compile figure is scaled from a 26-module sample measured on a quiet machine to all 122,458
modules, so allow plus or minus 30%; the 13.8 hour cloud build on 32 vCPUs bounds it at 442 vCPU-hours).

| Step | With Lean's kernel | With nanoda in place of Lean's kernel |
|---|---|---|
| Compile all 122,458 modules | about 330 CPU-hours (Lean's kernel check is inside this, about 15% of it) | about 280 (`-D debug.skipKernelTC=true`) |
| Comparator checks, 416 configurations | 80 (export, then Lean's replay, one thread each) | 46 (export 4 plus nanoda 42, for the 401 configurations that finish; the other 15 have no verdict) |
| Modules no solution imports | 0 extra (Lean's kernel already checked them in the compile) | 42 (nanoda, section 3h) |
| Total | about 410 | about 325 for the 416 configurations, about 365 with the other modules |

The nanoda total is about 20% lower than the Lean one for the same 416 checks and about 10% lower when nanoda also replaces Lean's kernel for every other module. The
larger difference is in wall time: with enough cores, the check phase of the nanoda pipeline is bounded by the single-threaded export (`PlanarPacking`: 14 minutes plus
11 minutes of nanoda on 64 threads, against 10.9 hours), while the build still needs about 280 to 330 CPU-hours of compiling. Nanoda's failures mean its totals do not cover
15 configurations.

**Hardware used:** a Framework Laptop 13 (13th Gen Intel Core) with a Core i5-1340P: 4 performance
cores with hyper-threading (up to 4.6 GHz) plus 8 efficiency cores (up to 3.4 GHz), so 12 physical
cores and 16 hardware threads, 60 GiB RAM, 39 GiB swap, a 2 TB WD Black SN850X NVMe drive (ext4),
Ubuntu 22.04.5 with kernel 6.8, on AC power. Under load the CPU package sat at its 100 C thermal
limit (load 20 to 30), so sustained speed was well below the chip's peak. A desktop CPU with real
cooling would probably finish sooner; that was not measured. The cloud machine was an AWS r7a.8xlarge
(32 vCPU AMD EPYC 9R14, 246 GiB, Ubuntu 24.04).

## 2. Mechanism: why the limit matters

Lean memory-maps module files. A process importing a module maps its `.olean` as one VMA (virtual
memory area). Modules built with Lean's module system (Mathlib, Lean core) also map `.olean.server`,
`.olean.private`, `.ir` and `.sig`, one VMA each. So

    VMAs per process ~ 40 + 5 * (module-system modules in the import closure) + 1 * (ordinary modules)

`vm.max_map_count` limits each process separately, not the machine. Checks: `import Mathlib` alone
has 10,744 module-system modules and 53,800 VMAs; Mathlib plus 9,272 OAI modules gave 65,681 (11,265
module-system modules x 5 + 9,269 ordinary modules); `Progressions.Main` predicted about 58.4k,
observed 58,571. Sampling can miss peaks, so sampled values are lower bounds, but a successful build
proves the true peak never passed the limit.

## 3. What was measured

| Run | Limit | Result | Peak sampled VMAs in one process | Wall time |
|---|---|---|---|---|
| import Mathlib | 65530 | ok | 53,800 | 11 s |
| ComparatorChallenges build | 65530 | ok, 9,409 jobs | 53,864 | 562 s |
| Progressions.Main build | 65530 | ok, 13,697 jobs | 58,571 | 14,116 s (machine shared and loaded) |
| Mathlib + 9,272 OAI modules | 65530 | fails (`failed to read file`) | 65,532 | 10 s |
| same file | 262144 | ok | 65,679 | 15 s |
| full OAI build, interrupted | 65530 | no failure in about 4,400 modules, stopped for disk | about 54,000 | about 97 min |
| `OstmannPrimes` build, then check | 65530 | both ok | 58,212 (build), 58,175 (check) | 65 min, 34 min |
| `MUBSix` build, then check | 65530 | both ok | 57,220 (build), 57,168 (check) | 3.9 h, 4.7 h |
| root `OAI.lean`, all modules built | 65530 | fails (`failed to read file`) | 65,532 | 13 s |
| same | 148000 / 150000 / 262144 | fails / ok / ok | 148,002 / 148,935 / 148,939 | 54 s / 64 s / 201 s |

Every Comparator configuration (416) built and checked at 65530; per-configuration numbers
are in section 3c and `results/cmp-all/configs.csv`.

Reproducibility: mapping counts depend on the imported file set and the Lean and Mathlib versions,
not on other processes. Wall times depend on machine load (load average 6-30 on 16 threads while
other work ran; the machine is a thermally limited laptop, see 3c) and each run was done once, so
there is no variance estimate.


## 3a. Whole-library prediction (all 122,875 modules, from import graphs only)

Tool: `tools/predict_vmas.py`, output `results/predicted-vmas.jsonl`. Model: 40 + 5 x (module-system
modules in the import closure) + 1 x (ordinary modules). External closure is 11,691 modules, of
which 11,472 use the module system.

- No module other than the root `OAI.lean` is predicted to exceed 65,530. The highest is
  `OAI.Combinatorics.Progressions.Main` at 61,124 (93% of the limit), then
  `Progressions.Results.FullLibrary` (61,014) and `OAI.NumberTheory.Ostmann.Main` (60,739).
- Predicted vs measured, deep modules: the measured peak is 0.957 to 0.960 of the prediction in all
  13 measurements (6 builds, 7 Comparator checks; e.g. `Progressions.Main` 61,124 predicted, 58,571
  sampled in the build, 58,559 in the check). The model therefore runs a steady 4.2% high;
  multiplying by 0.958 gives a calibrated estimate. The constancy suggests a systematic offset in
  the per-module cost, not noise.
- The fixed external part is about 56.3k (11,262 x 5). That leaves about 9,200 mappings for in-repo
  modules at the default limit; no non-root module has more than 4,774 in-repo modules in its
  closure. Family size does not matter by itself: only the size of one module's import closure does,
  and the biggest families are not the deepest ones.
- The root `OAI.lean` is predicted at 148,915 (about 142,700 after the 0.958 calibration): 11,379
  module-system externals x 5 plus 91,762 in-repo modules. It is the only module that needs more
  than the Ubuntu default. Measured with every module built: 148,940 mappings (fails at 148,000, succeeds at 150,000; section 3e).

- **Memory of the root import, measured at five sizes** (`tools/import_memory_probe.py`,
  `results/import-memory-probe.json`). Importing Mathlib plus a random sample of built OAI modules
  (and everything they import), then reading the process's memory split from `/proc`: Mathlib alone
  has 6.3 GiB resident, of which only 0.43 GiB is private heap and 5.89 GiB is mapped `.olean` file
  pages. With 9,271 OAI modules mapped (9.3 GB of `.olean` files) the process is 10.2 GiB resident:
  0.81 GiB private heap (0.042 MiB per OAI module) and 9.42 GiB mapped file pages (about 41% of the
  file bytes are touched). The mapped pages are shared and evictable page cache, not memory the
  process must keep. The sampling also shows how strongly modules depend on each other: 1,000 random
  imports already pull in 7,681 OAI modules, and 3,000 pull in 8,902. Extrapolating to the root's
  91,762 modules (70 to 90 GB of `.olean` files): about 4 GiB of private heap (range 3 to 8 GiB),
  and up to roughly 33 to 41 GiB of mapped file pages that the kernel can drop under pressure. So
  the root import needs little real memory; the earlier estimate of about 46 GiB resident was mostly
  page cache. The caveats are that the sample is of modules built so far and that extension state
  (simp sets, instances) could grow faster than linearly; the measured growth shows no sign of that
  up to 9,271 modules.

## 3b. Mathlib growth and when common Linux defaults will fail

Most of the mapping budget is Mathlib and Lean core, not the project code. Measured and derived
(Lean v4.34.1, Mathlib d13f23b723b):

- `import Mathlib` alone: 10,744 modules, 53,800 mappings, 82% of the Ubuntu/Debian default 65,530.
  The OAI modules that import a large part of Mathlib carry a fixed external cost of about 56.3k
  (11,262 module-system modules x 5, predicted; measured big modules 57-58.6k).
- Headroom left for a module that sits at the predicted worst case
  (`OAI.Combinatorics.Progressions.Main`, predicted 61,124, measured 58.6k): 4,406 mappings by the
  model, which is 881 more module-system modules. For bare `import Mathlib`, the default allows
  about 13,100 module-system modules, i.e. about 2,350 more than today.
- Growth of Mathlib (count of `Mathlib/**/*.lean` files at the last commit before each date, from
  the git history of the pinned checkout):

| Date | Files | Lean toolchain at that commit |
|---|---|---|
| 2024-01-01 | 3,782 | v4.5.0-rc1 |
| 2025-01-01 | 5,500 | v4.15.0-rc1 |
| 2025-07-01 | 6,558 | v4.22.0-rc2 |
| 2026-01-01 | 7,430 | v4.27.0-rc1 |
| 2026-07-01 | 8,226 | v4.32.0-rc1 |
| 2026-09-24 | 8,529 | v4.34.x |

That is about +1,700 files in 2024, +1,900 in 2025 and about +1,500 per year over the last nine
months. Almost all new Mathlib files become part of `import Mathlib` and of most deep project
modules.
- Extrapolation at about 1,500 new module-system modules per year (a straight-line assumption, not a
  forecast):
  - A bare `import Mathlib` crosses 65,530 in roughly 1.5 years (about 2,350 modules).
  - The deepest OAI modules, if they follow a newer Mathlib, cross it in roughly 0.6 years (881
    modules), since they already use 93% of the limit.
  - The root `OAI.lean` already exceeds it by more than a factor of two.
- What this does not depend on: the repository pins Mathlib, so nothing changes until the pin is
  moved. What it does depend on: (1) the per-module cost of 5 mappings is a property of Lean's
  module system and of this Lean version; before module-system builds the cost per module was lower,
  so older stacks had more headroom and a future Lean could reduce or increase it; (2) distribution
  defaults: Debian and Ubuntu keep 65,530, while Arch (1,048,576) and Fedora and Pop!_OS
  (2,147,483,642, the gaming value) are reported to be far higher (not independently verified).
- Mitigations: raise `vm.max_map_count` (cheap, `sysctl`), or Lean could map fewer files per module
  (merging `.server`/`.private`/`.ir`/`.sig`) or avoid mapping with `MMAP=OFF` at a memory cost (not
  yet measured here).

## 3c. Comparator results (all 416 configurations)

All 416 accepted, none rejected. Table: `results/cmp-all/configs.csv` (one row per configuration, written by `tools/export_results.py`);
`tools/cost_table.py` and `tools/cost_outliers.py` summarise it.

- **Check time** (active time, pauses and freezes removed): median 266 s, 90th percentile 1,036 s, 99th 5,764 s, maximum 39,131 s
  (`PlanarPacking`, 10.9 hours, 147 times the median); 80.1 hours in total. 329 checks took under 10 minutes; 12 took over an hour and
  together 32.7 hours. The slowest: `PlanarPacking` 39,131 s (13.1 GiB), `MUBSix` 16,981 s (26.1 GiB), `LaughlinFock` 7,329 s, `GeneralMahler`
  5,773 s, `TriangularEnergy` 5,713 s, `MatrixFields` 5,300 s, `TriangularGaussian` 5,378 s, `AtomicGaussian` 5,336 s. Check time is not predicted
  by closure size: `MUBSix` (3,381 modules) took 4.7 h and `OstmannComplete` (3,207) took 307 s.
- **Check memory:** median 6.5 GiB, 90th percentile 7.2 GiB, maximum 26.1 GiB (`MUBSix`); the largest are `MUBSix`, `ContinuumCoulombHardness` (20.3),
  `NuclearUltrapower` (19.6), `CoarseAssembly` (19.5), `ErdosReciprocal` (14.3), `SnakyTwentyOne` (13.4) and `PlanarPacking` (13.1).
- **Mapping counts in checks:** about 53.8k for any configuration, because the exporter imports Mathlib regardless of the solution; 56.4k to 58.6k
  for the deep ones. These agree with the model (section 3a).
- **Pauses.** The run was frozen by hand and by the memory valve several times; all are logged in `driver.log` (`tools/pause.sh`, `tools/resume.sh`,
  `tools/memvalve.py`). Raw records are left as measured; `tools/pauses.py` computes how much of any interval a pause covered, and `configs.csv` has
  `check_paused_s`, `check_active_s`, `build_paused_s` and `build_active_s`. All timings in this report are active times.
- **Second kernel:** section 3f.
- **Reading the build times.** `build_wall_s` in `configs.csv` is the time of the build step, not the cost of the configuration. It is near zero when the
  configuration's modules were already compiled for an earlier configuration or batch, and for configurations built in a batch it repeats the whole
  batch's time on every row, so it is not additive. The columns `batch_configs` and `modules_compiled_in_this_build` show which case applies; the
  `build_share_s` column divides a batch's time among its configurations. Real compile cost is better read from the per-module data below. Check
  times (`check_wall_s`) are per configuration and not shared.
- **Per-module data.** `results/module-times.csv.gz` has one row for each of the 79,201 modules with a recorded first compile in the raw Lake logs
  (too bulky to keep in git): area, first compile time in seconds, number of compiles, source size, in-repo closure size and predicted mapping count.
  The times are wall-clock under load, so they are upper bounds on isolated compile time; the 79,171 without a pause artifact sum to about 567
  module-hours. Modules that were only replayed from cache have no row.
- **How much module compile times vary.** The median is 13 s, the 90th percentile 36 s, the 99th 229 s, the 99.9th 1,145 s and the maximum
  4,968 s. 28% of the modules take under 10 s and 86% under 30 s, yet the slowest 1% account for 26% of all compile time and the slowest 10% for
  50%. By area, `OAI.Analysis` is 33% of the compile time (186 module-hours, 16,325 modules, 41 s a module on average), `OAI.Combinatorics` 22%
  (127 hours, 38 s a module), `OAI.NumberTheory` 8% (48 hours, 14,800 modules, 12 s a module) and `OAI.Probability` 8% (43 hours). Thirty modules
  show times inflated by a manual pause and are flagged `likely_pause_artifact`. The practical reading is that total build time is dominated by a
  small fraction of heavy modules, and that the critical path, not the average, decides how long a particular result takes.
- **Timing caveats:** the machine is a Framework 13 laptop with a Core i5-1340P (4 performance cores with hyper-threading plus 8 efficiency cores,
  16 threads), running at its 100 C thermal limit during builds (load 20 to 30). Other work ran at the same time and the run was paused by hand at
  times, so times are indicative, not benchmarks. Mapping counts are unaffected.

## 3d. What makes a check expensive

Across all 416 configurations (`tools/cost_outliers.py`, rows in `results/cost-outliers.csv`), the active Comparator check time has a
median of 266 s, a 90th percentile of 1,036 s, a 99th percentile of 5,764 s and a maximum of 39,131 s (10.9 h, `PlanarPacking`), 147 times the median.
Peak check memory has a median of 6.5 GiB, a 90th percentile of 7.2 GiB and a maximum of 26.1 GiB.

- **Size does not predict cost.** Check time against the summed compile time of the configuration's closure has a rank correlation of 0.51 (370
  configurations with at least 90% of the closure timed); a log-log fit has slope 0.46 and a residual spread of 0.37 decades (a factor of about
  2.3 either way). Check memory is unrelated to the solution file's source size (rank correlation -0.01).
- **The outliers are specific proofs.** Checks 6 to 18 times slower than the trend predicts: `PlanarPacking` (18 times), `GeneralMahler` (9.8),
  `LaughlinFock` (8.3), `TriangularEnergy` and `MUBSix` (6.4), `MatrixFields` (6.2), `TriangularGaussian` (6.1), `AtomicGaussian` (6.0). The largest
  memory users are listed in section 3c.
- **Export size is the best simple predictor.** `tools/export_probe.py` measured the size of every configuration's solution export (227 GB in
  all; median 0.5 GB, largest 8.1 GB) without running a check. The rank correlation of check time with export bytes over all 416 is 0.67 (with
  expression nodes 0.67, theorem records 0.69, natural-number literals 0.34, and with the number of `of_decide_eq_true` applications, the proof term
  `decide +kernel` leaves behind, 0.45); check time per exported MB has a median of 0.56 s and ranges from 0.25 to 33 s (`tools/export_vs_check.py`).
  A log-log fit on export bytes has slope 0.93 and a residual spread of 0.36 decades. The checks far above that fit are the ones that make the
  kernel compute: `SnakyCertificate` (40 times the fit), `SnakyTwentyOne` (37), `CycleCliqueRamsey` (33, 17,023 `of_decide_eq_true` applications in a
  186 MB export), `UniversalTensorSquares` (27, 49,434 applications), `LaughlinFock` (19), `SnakyConditional` (17) and `PlanarPacking` (17, 251,693
  applications). The count of these applications is a hint, not a rule (`BorsukNine` has 6,616 and took 257 s). The size of a term does not show the cost
  of its evaluation either: the single slowest declaration in `SnakyTwentyOne` is 18 lines in the export and takes nanoda 86 s (section 3f).
- **Source properties explain about half of the variation.** An earlier fit of log check time on the closure's source size, count of `decide +kernel`
  and count of certificate modules (`tools/predict_check_cost.py`) reached R^2 0.49 with a residual spread of about a factor of 2.1. It
  underestimated the slowest few checks by factors of 2 to 3.4 (`PlanarPacking` was predicted at 16,500 s before its check finished and measured
  39,131 s).

What the expensive modules contain, from reading samples of them:

- `MUBSix`: the solution file `OAI/Analysis/MutuallyUnbiased/Main.lean` is 1.3 KB and states one
  theorem, but imports 3,382 modules (summed compile time about 217,000 s). A sample generated
  module, `MixedSemantics/Canonical296.lean` (125 KB, 128 theorems, 248 uses of `decide +kernel`),
  proves equalities between "mixed moments" of explicit small integer matrices by permuting rows and
  columns. The permutation identities are closed by kernel evaluation and the rest by `rfl`.
- `CycleCliqueRamsey`: `Construction/CertificatesK15Part001.lean` is 5.6 MB with 10,797 uses of
  `decide +kernel`, and consists of explicit layout data (chains, cliques) for a fixed graph size.
- `PlanarPacking`: `Certificate/LowBlock15_10.lean` is 247 KB with 1,188 uses of `decide +kernel`
  and integer interval enclosures that certify numerical bounds. The configuration's closure has 446
  modules with "Certificate" in their names and 255,199 uses of `decide +kernel`. Its check took
  39,131 s of active time (47,310 s wall) and peaked at 13.1 GiB, although it used about 5.8 GiB for
  most of the run, so its memory grew late.

In Lean the proof term is itself a certificate that the kernel re-checks without repeating the
search, so checking is usually far cheaper than building (the median check is about 4 minutes), but
it is not bounded: proofs that make the kernel evaluate large computations (`decide +kernel`) can
cost hours. The expensive modules above look like machine-generated finite certificates checked by
kernel computation, a different style from structural proofs, with none of the sampled files using
`native_decide`. If so, the cost of a check would follow how much kernel evaluation reaches the
exported terms rather than how long the sources are. That is a hypothesis from three samples and the
export-size data above. `GeneralMahler` and `LaughlinFock`, the largest remaining outliers by ratio,
have not been read.

## 3e. The root import (`import OAI`): what it needs

`OAI.lean` imports 91,762 modules. A process that imports it maps one file per ordinary module and
five per module-system module (Mathlib and Lean core), which predicts about 149,000 mappings against
the default limit of 65,530 (section 3a). Measuring it needs only some of the build outputs:

- **The `.olean` files of every imported module, uncompressed on disk.** They are memory-mapped,
  about 0.66 MB each (72.4 GB for the 109,152 built modules, plus Mathlib's own in its package
  directory). Memory is not the constraint: the private heap is predicted at about 4 GiB and the
  rest is evictable file pages.
- **Nothing else.** The `.ilean` files (the editor's index), the `.trace` and `.hash` files (Lake's
  bookkeeping) and everything in `.lake/build/ir` are not read by an `import`. The `ir` directory
  holds three files per module: `.c` (about six times the source size, 30 KB on average), `.c.hash`,
  and `.setup.json`, the input Lake passes to the compiler. A `.setup.json` lists the `.olean` and
  IR paths of every transitive import, about 730 bytes per import, so it is about 6 MB for a module
  with 9,000 imports. They are 99.5% of the bytes in `ir` (60.4 of 60.7 GB for 9,618 modules; the C
  was 0.3 GB) and are transient: needed while the module compiles, not afterwards.
- **A built `OAI` module.** `lake build OAI` compiles the root module itself, which performs the
  import, so at the default limit the build is expected to end with the mapping failure
  (`failed to read file ... .olean`, as seen in earlier tests) after all its dependencies are built.

State at the end of the Comparator run: 85,301 of the 91,762 modules are built. The 6,461 that are
not (including `OAI`) belong to no configuration's import closure: 58 MB of source in 177 families,
mostly Analysis (1,634), Geometry (1,325), Probability (919) and Combinatorics (712), and only 5
with "Certificate" in the name. From the compile times of built modules in the same areas
(`tools/root_build_status.py --estimate`) they need about 31 module-hours, which at the 10.8-fold
parallelism of the Comparator run (567 module-hours in 52.5 hours of build time) is about 3 hours,
and about 40 GB of transient `.setup.json` and C files (about 1.6 GB archived).

First trial, before the missing modules are built (`tools/root_import_trial.py`): one process
importing Mathlib and all 85,301 built modules reachable from `OAI.lean`, at the default limit of
65,530. It fails after 16.7 s with
`failed to read file '.../OAI/Probability/SKBarriers/Locking/NarrowClockAlgebra.olean'` (the file
exists and is readable), with the sampled per-process mapping count at 65,532, which
`tools/vmamon.py` classifies as the mapping limit. Mathlib's 10,744 modules account for about 53,800
mappings, so by the model of section 2 the limit is reached after roughly 11,800 OAI modules, about
14% of the 85,301 (the position of the failure was not measured).

Second trial, same state, with the limit raised to 262,144 and the real `OAI.lean` (its 914 imports
in the repository's order): it stops after 7.8 s with
`object file '.../OAI/AlgebraicGeometry/CharacterVarieties.olean' of module OAI.AlgebraicGeometry.CharacterVarieties does not exist`,
with the sampled mapping count at 55,858 (Mathlib's 53,800 plus about 2,000 OAI modules). The
mapping limit is therefore out of the way, and what stops the import is the first unbuilt module in
the import order, long before the 65,530 mappings of the first trial could be reached.
(`tools/root_import_trial.py --root` under `tools/with_maxmap.sh`.)

Building the missing modules (`tools/root_build.py`: the memory valve of `tools/memvalve.py`, six compile
slots on ten logical CPUs, the C and import-list files archived after each chunk) took 91,761 modules to
built, every module of `OAI.lean` except the root `OAI` itself. The compiles took about 9 hours of wall time in
five chunks (74 s for a 30-module pilot, then 2,605 s, 8,117 s, 8,145 s, 9,007 s and 4,703 s), three times the
3 hours estimated above: the estimate assumed the 10.8-fold parallelism of the Comparator run, while here the
six slots were often idle behind a single slow module (`OAI.Analysis.FreeWords.UltraExpectationFull` alone
took over an hour on one core). Peak sampled mappings in any build process were 53,868 to 57,276, below the
default limit as for every other build.

Third trial, everything built: the real `OAI.lean` run as `lean OAI.lean` under `tools/vmamon.py`
(`tools/root_import_trial.py --root`; the root compile is the import, nothing else), results in
`results/root-import-trial/`:

| `vm.max_map_count` | outcome | wall time | peak mappings (sampled) |
|---|---|---|---|
| 65,530 (default) | fails: `failed to read file '.../OAI/Analysis/Conductivity/Sources/LocalPiola.olean'` | 13 s | 65,532 |
| 140,000 | fails: same message, for another module | 52 s | 140,002 |
| 148,000 | fails: same message | 54 s | 148,002 |
| 150,000 | succeeds, exit 0 | 64 s | 148,935 |
| 160,000 | succeeds, exit 0 | 73 s | 148,939 |
| 262,144 | succeeds, exit 0 | 201 s (cold file cache) | 148,939 |

- **The root import needs a `vm.max_map_count` between 148,001 and 150,000**: about 148,940 mappings in
  the single `lean` process, against 143,000 to 149,000 predicted from the whole-library model
  (section 3a). A limit of 262,144 has a margin of 1.76. Sampled peaks are lower bounds; the failure at
  148,000 and the success at 150,000 bracket the true need.
- **Memory:** the `lean` process's peak resident size was 34 to 37 GiB, almost all of it file-backed
  pages of the memory-mapped `.olean` files that the kernel can evict, and the lowest `MemAvailable` on
  the 60 GiB machine was 37.0 GiB. The importing process needs a big page cache, not a big heap.
- **Time:** 64 to 73 s with the files in the page cache, 201 s with a cold cache (25 to 28 s of user
  time, the rest system time for the mappings).

## 3f. The second kernel (nanoda) and the cost of Lean's own

Comparator can check a solution with a second, independent kernel in addition to Lean's built-in one (`enable_nanoda: true`; only 2 of the 416
configurations set it). It exports the solution once (`lean4export`, a text file listing the declarations the theorem depends on), runs nanoda
on the export with 4 threads (the number is hard-coded in Comparator), then replays the same export through Lean's kernel. There is no option to skip
Lean's replay. Where the time of a check goes, on 13 paired laptop runs: 11% nanoda and 51% Lean's replay; the rest is the build check, the export and start-up.

**Paired timings** (laptop, nanoda on 4 threads, Lean's replay on one):

| Configuration | Export | nanoda | Lean replay | nanoda / Lean |
|---|---|---|---|---|
| ThreeStateSupercritical | 230 MB | 2.7 s | 12.5 s | 0.22 |
| GaussianFiniteEntropy | 422 MB | 5.6 s | 26.4 s | 0.21 |
| NavierStokesAlternating | 512 MB | 9.4 s | 57.4 s | 0.16 |
| PermanentCubic | 753 MB | 24.2 s | 107.2 s | 0.23 |
| Heisenberg | 864 MB | 27.1 s | 137.5 s | 0.20 |
| CriticalStripMass | 833 MB | 42.6 s | 173.3 s | 0.25 |
| SnakyConditional | 72 MB | 128.9 s | 633.4 s | 0.20 |
| CycleCliqueRamsey | 192 MB | 701.5 s | 3,029 s | 0.23 |

So nanoda takes 0.16 to 0.25 of Lean's replay time on these (4 to 6 times faster), and its memory is small (mostly 0.2 to 1.4 GiB, 5.6 GiB for the `Snaky` exports, against about 6 GiB for
the exporter) but grows with threads. Nanoda does about as much CPU work as Lean's replay; its advantage is that it parallelises. Results for all configurations
are in the next paragraph.

**Paired sweep over 390 configurations** (`tools/kernel_pair_sweep.py`, `results/kernel-pair-sweep.jsonl`: one laptop, each export made once, Lean's replay on one thread, nanoda on 4
threads, the configurations whose laptop check took over 2,000 s and the three known failures left out). Nanoda accepts 381; the nine it does not are listed below, and Lean accepts all nine.
On the 380 where both finished, the median time of nanoda as a fraction of Lean's parse and replay is 0.21, the lowest 0.12 (`Saxl`), and the totals are 10.3 hours of Lean replay against
2.75 hours of nanoda. Nanoda is slower on two: `ArnoldCounterexample` (855 s against 218 s, ratio 3.7) and `PartitionPrinciple` (88 s against 39 s, 1.9). Export time is not included; over the whole sweep the export
(`lean4export`, one thread) took 27% of the replay time.

**How nanoda uses threads.** Its threads take the export's declarations in order from a shared counter (`ext/nanoda_lib/src/tc.rs`), so parallelism is across
declarations and the limit is the longest declaration plus the serial reading of the export (about 5 s per GB). A quiet 64-vCPU machine, nanoda only
(`tools/nanoda_scaling.py`, `results/nanoda-scaling-cloud/`):

| Configuration (export) | 4 threads | 8 | 16 | 32 | 64 | Memory at 4 / 64 threads |
|---|---|---|---|---|---|---|
| SnakyTwentyOne (77 MB) | 193.7 s | 137.6 | 112.5 | 100.2 | 95.5 (2.0x) | 5.6 / 7.6 GiB |
| CycleCliqueRamsey (186 MB) | 681.5 s | 345.8 | 183.8 | 101.6 | 64.9 (10.5x) | 1.0 / 6.4 GiB |
| MatrixFields (612 MB) | 431.0 s | 223.3 | 122.4 | 68.6 | 43.7 (9.9x) | 2.1 / 9.5 GiB |
| PlanarPacking (3.85 GB) | about 9,900 s (model) | | | | 672 s, 58.8 cores, 40.9 GiB | |

`SnakyTwentyOne` stops scaling because one declaration (`OAI.SnakyPrototype.Certificate21.child_envelope_sub_727._proof_1_1`, 18 lines of export)
takes 86 s of the 533 s of work; 64 threads finish at 95 s. `PlanarPacking` has 847,817 declarations, 39,559 s of work, a longest declaration of 15.8 s
and 54 s of serial setup, so 64 threads run it in 672 s, against 10.9 hours for Lean's replay (the laptop's whole check). CPU time grows with threads
(+43% from 4 to 64 for `CycleCliqueRamsey`). `tools/nanoda_thread_model.py` predicts the wall time at any thread count from one run's per-declaration times
to within about 1% (`SnakyTwentyOne`: predicted 138.6, 113.1, 100.5 and 94.4 s at 8, 16, 32 and 64 threads, measured 137.6, 112.5, 100.2 and 95.5 s). The
size of a declaration in the export does not predict its cost (`tools/nanoda_cost_proxy.py`: for `SnakyTwentyOne` the proxy puts none of the 10 slowest
declarations in its top 50), so the thread count has to come from a first run's times.

**Where nanoda fails.** Fifteen configurations do not complete (and `MUBSix`, which did not finish in 90 minutes at 4 threads, finishes in 2,176 s at 8 threads). With the pinned nanoda
(3a24072) the checker thread's 16 MiB stack overflows (Comparator reports "nanoda kernel rejected the solution" and exit 134, which reads as a verdict on the proof). Every
failure is a few declarations; all their dependencies check normally. Each begins in the per-declaration log and never ends:

| Group | Declarations that never finish |
|---|---|
| RoundTables (8 configurations: `DirectedFeedback`, `UniqueGamesTheorem`, `BinPackingGap`, `VertexCover`, `IndependentSets`, `MinUncut`, `PerfectCompleteness`, `OptimalMaxCut`) | `...Foundations.PCP.RoundTables.sizeFactor_positive`, `...build_size_le` |
| `Catalan` | `OAI.InternalCatalan.fixedDeterminantPrimeCutoff_ge_260`, `...fixedDeterminants_residue_ne_zero_of_lt` |
| `Laughlin`, `LaughlinPlanar`, `LaughlinFock` | `OAI.Laughlin.Certificate.computeLDL_21_*_*._proof_1_1`; `OAI.LaughlinFock.fourLDLChecked_*._proof_1_1` |
| `KMedianThreshold` | `OAI.MetricKMedian.PCP.Compiler.CloudSpec.padding_code` |
| `SquareDifference` | `OAI.SquareDifference.tupleEta_le`, `tupleSubLaw_full`, `tupleLaw_decomposition`, `tupleGoodLaw_probability` |
| `ContinuumCoulombHardness` | `OAI.ContinuumCoulomb.QuantumRawExchange.budgetProgram`, `matrixBudgetProgram` |

How they fail, where it was measured: with a stack of 1 GiB per thread (a local change; the stack size is a compile-time constant) `DirectedFeedback` and `UniqueGamesTheorem` still
overflow after 131 s at 25 GiB, and with 16 GiB `UniqueGamesTheorem` panics after 1,874 s at 285 GiB with `index 2147483648 exceeds 31-bit capacity` (nanoda's pointer type has a
31-bit index); `Catalan` panics the same way after 2,014 s at 259 GiB. `Laughlin` was killed at 151 GiB, `LaughlinFock` aborted at 127 GiB and `LaughlinPlanar` reached 175 GiB before it
was suspended and ended by a four-hour timeout. For the other six RoundTables configurations, `KMedianThreshold`, `SquareDifference` and `ContinuumCoulombHardness` nanoda exits with an error after
49 to 125 s (a 1 GiB stack); only the unfinished declarations were recorded.

A 7.7 MB export of `sizeFactor_positive` alone reproduces the overflow in under a second with the stock nanoda (`results/nanoda-repro/`); Lean's replay of the same file takes 0.38 s. A
gdb backtrace shows `TypeChecker::whnf` and `TypeChecker::try_reduce_nat` alternating 58,000 times each; the export is too small to hold a term that deep, so this is a reduction that
does not terminate or an unshared expansion, not a deep term. An export of the single declaration `OAI.Problem355.MainDigitLaw.sampled_orbit_det_gt` (247 MB, section 3h) gives the same
picture: 1,864,067 frames, 932,010 of `whnf` and 932,007 of `try_reduce_nat`. The Laughlin, `KMedianThreshold`, `SquareDifference` and `ContinuumCoulombHardness` groups have no backtrace yet, so
whether all fifteen share one cause is open. The main thread has its own stack limit, separate from the checker threads': on the Problem355 export it overflows after 35 s unless `ulimit -s unlimited`
is set. Everything is written up in [nanoda_lib issue 55](https://github.com/ammkrn/nanoda_lib/issues/55); the text is in `results/nanoda-stack-test-cloud/nanoda-issue-draft.md`.

**The long configurations on nanoda alone.** The 18 configurations whose laptop check took over 2,000 s were exported and checked with nanoda on 8 threads, with a 1 GiB checker
stack, 10 at a time on a 32-vCPU machine (`tools/cloud_long_nanoda.sh`, `results/long-nanoda/`). Fifteen pass; end to end (export plus nanoda) they take 22,396 s against 79,022 s for the
laptop's Lean-based checks, 3.5 times less in all, and the single-threaded export is the floor:

| Configuration | Laptop check (Lean) | Export | nanoda, 8 threads | Export + nanoda | Speed-up | Peak memory |
|---|---|---|---|---|---|---|
| MUBSix | 16,981 s | 1,520 s | 2,176 s | 3,696 s | 4.6x | 8.9 GiB |
| UniversalTensorSquares | 13,548 s | 160 s | 2,925 s | 3,085 s | 4.4x | 20.8 GiB |
| LaughlinFock | 7,329 s | 160 s | did not finish | | | 127 GiB when it ended |
| GeneralMahler | 5,773 s | 151 s | 1,287 s | 1,438 s | 4.0x | 5.9 GiB |
| TriangularEnergy | 5,713 s | 151 s | 2,396 s | 2,547 s | 2.2x | 16.4 GiB |
| TriangularGaussian | 5,378 s | 146 s | 2,339 s | 2,484 s | 2.2x | 16.8 GiB |
| AtomicGaussian | 5,336 s | 146 s | 2,348 s | 2,494 s | 2.1x | 15.6 GiB |
| CoarseAssembly | 4,351 s | 148 s | 545 s | 692 s | 6.3x | 9.3 GiB |
| SKRatio | 4,154 s | 150 s | 1,729 s | 1,879 s | 2.2x | 4.9 GiB |
| Laughlin | 3,596 s | 414 s | did not finish | | | 151 GiB when it ended |
| LaughlinPlanar | 3,468 s | 395 s | did not finish | | | 175 GiB when it ended |
| LaughlinGap | 3,172 s | 185 s | 913 s | 1,098 s | 2.9x | 7.5 GiB |
| StrongKadisonKastler | 2,914 s | 207 s | 371 s | 578 s | 5.0x | 2.2 GiB |
| FactorGeneration | 2,603 s | 68 s | 133 s | 200 s | 13.0x | 1.0 GiB |
| ErdosReciprocal | 2,472 s | 763 s | 738 s | 1,501 s | 1.6x | 10.5 GiB |
| DuttaDomain | 2,356 s | 106 s | 79 s | 185 s | 12.8x | 1.1 GiB |
| RelativeGeneration | 2,228 s | 67 s | 99 s | 166 s | 13.4x | 1.0 GiB |
| OstmannPrimes | 2,044 s | 233 s | 118 s | 351 s | 5.8x | 2.2 GiB |

The three that fail are the Laughlin family above. The speed-up is smallest (1.6 to 2.2 times) where one stretch of work does not parallelise (`ErdosReciprocal`, `TriangularEnergy`,
`TriangularGaussian`, `AtomicGaussian`, `SKRatio`) and largest (13 times) on the small ones.

**Skipping Lean's kernel check while compiling.** Lean has the option `debug.skipKernelTC` ("skip kernel type checker ... may compromise soundness"),
which adds declarations without the check; neither Lake nor `lean` has an option to choose another kernel. A copy of a module compiled with
`-D debug.skipKernelTC=true` exports identically (byte for byte, module name aside), nanoda accepts it, and a deliberately false theorem added through
`addDecl` is accepted by that build, rejected by the normal build, and rejected by nanoda from the export (`tools/skip_kernel_test.py`). On a stratified
sample of 26 built modules compiled both ways (`tools/skip_kernel_sample.py`) the compile CPU time falls by 16% and the wall time by 27%, weighted by each
size class's share of the library's compile time (3% in the fastest class, 26% CPU and 55% wall in the slowest). Lean's own profiler puts the time in
the "type checking" category (the kernel adding declarations) at 3.3% of the build time over the 30,810 modules built with profiling on the cloud
(`tools/profile_from_builds.py`, `results/cloud-profile/profile-by-module.csv`); that category leaves out kernel work done inside `decide +kernel`.

**Skipping Lean's replay in Comparator.** A local patch adds a configuration field `skip_builtin_kernel` (`tools/patches/comparator-skip-builtin-kernel.patch`;
it refuses to run without an external kernel); the same request is open upstream as leanprover/comparator issue 97. The replay is about half of a typical
check and most of a long one, so with nanoda alone `PlanarPacking` is 11 minutes on 64 threads instead of 10.9 hours.

**What an alternate-kernel pipeline looks like in these terms.** Build with `debug.skipKernelTC` (about 15% less compile CPU), export each solution once (227 GB of exports in all; about 4 CPU-hours
in total for the 401 that finish, 14 minutes for `PlanarPacking`), and check with nanoda at a thread count chosen from the first run's times (46 CPU-hours for the 401 configurations that finish,
against 80 hours of Lean replay and export on one thread for all 416, with the long tail collapsing from hours to minutes). The costs are the 15 configurations above, memory that grows with
threads (41 GiB for `PlanarPacking` at 64 threads), and that the build no longer has Lean's kernel as a check, so the external kernel carries all the weight. The correctness questions are
not addressed here.

## 3g. The cloud runs

All on AWS us-east-1 (about $85 of spend, estimated from hourly prices; the account's budget alarm was $100 a month). A pilot on an m7a.2xlarge (8 vCPU) built and
checked `MatchingFPRAS` (416 modules) and `FourierLLogL` (157): compiling was 3.7 and 4.8 times faster than the laptop's first-build times (an upper bound on the gain,
because those times came from a loaded machine), and the checks 1.35 and 1.05 times (the kernel is single-threaded). The full build used an r7a.8xlarge (32
vCPU, 246 GiB, 1.6 TB gp3), set up from nothing in 4.5 minutes by `tools/cloud_bootstrap.sh`.

- **Result:** every `OAI` module (122,458, the root `OAI` included, at `vm.max_map_count` 262,144) was built in 13.8 hours, with no failures. The 107,978 modules
  of the configuration closures took 7.4 hours of that. The throughput was about 50 laptop-module-hours of first-build time per hour, 4.7 times the laptop's
  10.8. The machine's default `vm.max_map_count` is 1,048,576 (the Ubuntu 24.04 AWS image), so default-limit runs set it to 65,530.
- **What mattered:** (1) Lake starts every ready compile at once; with no cap the load average reached 130 on 32 vCPUs and some compile processes had 900
  threads. A throttled toolchain (`tools/make_throttled_sysroot.sh`, 32 compile slots shared across all Lake processes) plus `-j4` per compile fixed that.
  (2) Lake cannot prioritise, so `tools/priority_build.py` runs several `lake build` processes in order of predicted check time, longest first, and only
  starts one whose unbuilt modules do not overlap a running build's, so no module is ever compiled twice at once. (3) Checks beside builds are timed under
  load: `CycleCliqueRamsey`'s nanoda phase took over 49 minutes with six checks sharing 8 pinned vCPUs, against 11 minutes alone. Nanoda wants 4 vCPUs while it runs, so admit checks by thread budget,
  not by job count.
- **Disk:** of 599 GB used, 497 GB was transient `.setup.json` files. Without them the whole build is 116 GB (68 GB of `.olean`/`.ilean`, 13 GB of
  packages, the `.c` files Lake tracks), and a copy to a 250 GB volume was verified by file counts, 200 random `.olean` files compared byte for byte, and five
  random Comparator checks (accepted, no module rebuilt).
- **Cost shape:** compiling is wide and short, while checks are single-threaded and long, so one large machine sits mostly idle through the tail; separate
  right-sized machines for checks, fed from exports, would cost less (a nanoda-only pass of all 416 on one 64-vCPU machine is an hour or two).
- **Later runs on the same volume:** the 40 earliest cloud checks were repeated alone on a 16-vCPU machine (all accepted; median time 0.59 of the first, which had shared the machine with the
  build); the 18 long configurations ran on a 32-vCPU machine in 4.3 hours of wall time (section 3f); and the modules no solution imports ran there in about 4 hours of wall time (section 3h). The 250 GB volume with the
  finished build is kept (about $0.8 a day stopped); the instances stop themselves and a time guard stops them regardless.

## 3h. The modules no solution imports

Comparator, and so every nanoda result above, checks only what the 413 distinct solution modules import: 107,977 of the 122,458 `OAI` modules (88.2%, `tools/solution_coverage.py`,
`results/solution-coverage.json`). The other 14,481 are concentrated in Geometry (4,223 of 14,057), Analysis (2,307 of 26,566), Probability (2,281 of 12,971), MathematicalPhysics (1,544 of 6,736) and
Combinatorics (1,341 of 16,614); the list is `results/uncovered-modules.txt`. A module a solution imports can still hold declarations the solution does not use, so 88% is an upper bound on
declaration coverage. Lean's own kernel checked every module during the build, so this is a test of nanoda, not a gap in Lean's check.

`tools/uncovered_check.py` takes them in 58 batches of 250 modules (the root `OAI` declares nothing itself), lists each module's own declarations (`tools/list_module_decls.lean`), exports them with
`lean4export` (each export also carries their dependencies, 0.6 to 2.6 GB) and runs nanoda (8 threads, 1 GiB checker stack). A batch whose names do not fit one command line becomes several pieces, and
a batch whose modules cannot be imported together is split: some modules declare the same name, and Lean refuses to import both (the first attempt with 500 modules failed on
`OAI.RegularPointCoordinates.renyiIntegral_eq_inverse_density`). Result on the 32-vCPU machine, six batches at a time: 77 pieces, 76 accepted (about 437,000 named declarations, plus their auxiliary proofs; 42
CPU-hours, 1.3 of them export), one failed.

- **`OAI.SepticProfile` (the largest piece of work):** 16 pieces, all accepted. These are the `Transonic` modules, "relativistic transonic profiles for the septic wave equation" in the module header, the
  profile input for a paper on blowup for the defocusing septic wave equation: interval boxes with integers of 60 to 280 digits (`Q = 10^60` or `10^280`), checked by `norm_num`, one declaration per bound.
  Pieces of about 18,500 named declarations (260,000 to 290,000 counting auxiliary proofs; 735,000 for the larger pieces) took 7 to 17 minutes each, those of about 19,900 took 45 minutes. Memory stayed at 3 to 4 GiB, and the slowest single
  declaration took 3.2 s: it is the number of declarations, not any one of them, that takes the time.
- **The failure:** `OAI.Problem355.MainDigitLaw.sampled_orbit_det_gt` in `OAI/Geometry/HeilbronnTriangle/MainDigitBadTripleBound.lean` (a bad-triple bound for the Heilbronn triangle problem, going by the names:
  a 3 by 3 integer determinant above a threshold unless two labels are equal). Its export alone (247 MB, 35,715 dependencies that all check) fails in nanoda: the main thread overflows after 35 s unless
  `ulimit -s unlimited`, and then a checker thread overflows after 488 s and 35 GiB with a 1 GiB stack, in the same `whnf` and `try_reduce_nat` alternation (`results/nanoda-repro/problem355-gdb-backtrace.txt`,
  `tools/isolate_decl.py`). Lean's kernel accepts it in the build.

## 4. What is in the library, and what OAI.lean is

- 122,458 `.lean` files under `OAI/` (26.06 M lines, 1.57 GB) plus 416 files in
  `ComparatorChallenges/`.
- `OAI.lean` is a pure aggregator: 913 `import OAI...` lines and one blank line. It has no
  mathematical content. Its only effect is that `lake build OAI` compiles everything reachable from
  it, and compiling that one file loads all 91,762 reachable in-repo modules into a single process.
- Not every file is reachable from `OAI.lean`: 30,697 of 122,459 are not (list:
  `results/oai-unreachable-from-OAI.lean.txt`). They are concentrated in: NumberTheory 9,519 of
  23,530; MathematicalPhysics 5,937 of 6,736; Geometry 3,602 of 14,057; Probability 3,641 of 12,971;
  Analysis 3,230 of 26,567; Combinatorics 2,846 of 16,614; MeasureTheory 1,742 of 2,950;
  CategoryTheory 140 of 312. The per-area libraries in `lakefile.lean` (`OAI.Analysis` and so on,
  using
  `globs := #[`OAI.X.+]`) do cover every file. So "the entire library" has at least three meanings: `lake
  build OAI` (91,762 modules), all per-area libraries (about 122k), and what the Comparator configs
  need (below).

## 5. Three different things "verifying" can mean

These are different claims, and a pass at one does not imply the others.

1. **The library compiles.** Lean's kernel accepts every declaration in every module. This shows the
   proofs are internally consistent given the statements as written. It does not show the statements
   mean what the paper says, and it would not catch a module that adds its own axiom or hides a
   `sorry` unless you inspect it.
2. **A Comparator check passes.** Comparator (with `landrun` sandboxing and `lean4export`) compares
   a small, human-readable *challenge* file, whose theorem statement is `sorry`'d, against a
   *solution* module in the big library. It checks that the solution proves the same statement, that
   it uses only the permitted axioms (here propext, Quot.sound, Classical.choice in all 416
   configs), and replays the proof externally from an export of the environment, optionally with a
   second independent checker (`nanoda`, enabled in only 2 configs). This is the strongest
   mechanical check on offer: it guards against the solution changing definitions, adding axioms, or
   relying on a Lean implementation quirk. It is what the repo's README means by verifying a result.
3. **The statement matches the paper's claim.** This is human judgement about whether the short
   challenge statement faithfully expresses the manuscript's theorem. The repo's scope notes
   (`lean/docs/NNN.md` in openai/math) say what each configuration does and does not cover. Some
   configs verify only supporting results; the Comparator README names five
   (`CharacterVarietiesAllSeamsSupport`, `CartierChartCompactnessSupport`,
   `SurfaceConeCandidateSupport`, `TraceIdealTransportSupport`, `HoneycombBridgeMassSupport`).
4. **The paper's mathematics is correct.** Not established by any of the above. Formal proof of a
   faithful statement supports the theorem, but a mismatched statement could be proved while the
   claimed result stays unproved.

Level 1 is weaker than level 2. Level 2 can be restricted to the configs that check a manuscript's
main claim as opposed to a supporting lemma. Level 3 is outside what machines check, and level 4 is
outside what this project addresses.

**Scope of a Comparator run.** The challenge files import little; each config names a separate
`solution_module` (for example `OAI.GroupTheory.ArtinCAT0.Main`) that the challenge file does not
import. Across the 416 configs (413 distinct solution modules), the combined import closure of the
solution modules is **107,978 modules (23.4 M lines)**, all of which are built. Level-2 verification of everything therefore needs about as much as a full build,
and more than `lake build OAI` covers (91,762): 23,435 of the modules are in a configuration's closure but not reachable from `OAI.lean`.

## 6. Can a full build fit on this machine?

Free space on the test machine's `/home` was 124.7 GB before the work started and stayed between 37
and 82 GB during the Comparator run.

| Item | Per module | If 108k modules |
|---|---|---|
| generated build files (`.lake/build/ir`: `.setup.json`, `.c`, hashes) | about 5.4 MB | about 580 GB |
| `.olean`, `.ilean`, hashes and traces (`.lake/build/lib/lean`) | about 0.72 MB | about 79 GB (measured: 72.4 GB of `.olean`, 6.0 GB of `.ilean`, 0.7 GB of traces for 109,152 modules) |

- The generated files in `ir` are outputs Lake tracks: moving one away made Lake rebuild that module
  (3.6 s) when asked again, without rebuilding its dependents. Deleting C files as each batch
  finishes saves disk but means a later plain `lake build` will recompile those modules; checks that
  read the `.olean` files directly are unaffected.
- Compression: the generated build files compress to 4.3% with zstd (one archive: 58,038 MB to 2,478
  MB for 9,617 modules), so about 580 GB would be about 25 GB, but only on a compressing filesystem
  (this one is plain ext4) or as an archive at rest. `.olean` files compress to 33% (gzip) and 24%
  (xz), `.ilean` to 12%; but `.olean` files are memory-mapped at run time, so they must be stored
  uncompressed while in use. At rest an olean archive of 105 GB would be about 30 GB.
- Measured pace on the laptop: about 1,750 to 1,900 modules an hour with all 16 threads busy, 3.8 days for
  the whole Comparator run; the 6,460 modules only `OAI.lean` needs took about 9 hours more.
- What worked: each batch's generated build files are compressed (verified), removed after its
  checks, and restored for later builds, so disk never ran out. The `.olean` files (about 105 GB for
  the full closure) must stay uncompressed; the root `OAI.lean` additionally needs them all present
  at once. The cloud alternative was used (section 3g): one 32-vCPU machine built everything in 13.8 hours.

## 7. Other Lean libraries, for context

Mathlib (leanprover-community/mathlib4): 9,112 files, 2.4 M lines, about 965 distinct authors in
git, 137,995 definitions, 290,317 theorems, 772 contributors on the stats page. Changes enter by
pull request, review and maintainer approval, and a bot merges them; review capacity is the
bottleneck (400+ PRs in the queue per a Mathlib Initiative posting). OAI relies on about 94% of
Mathlib's files (8,530 of 9,112), 100% of Lean core, and parts of 18 other packages (about 11,700
external modules reached transitively, 2,693 imported directly).

Young very large libraries in the dependency tree have no comparable review: TauCeti (9,994 files,
2.2 M lines, first commit 2026-06-02), AINTLIB (2,826 files, 2 authors, 10,334 commits in under
three months), ClassFieldTheory (1,713 files, 21 commits), and a family of `lana-agents/*`
repositories created in July 2026. All four are confirmed to include AI contributions. Human-led
project libraries (PrimeNumberTheoremAnd, 83 authors; carleson, 39; sphere-eversion, 21) are one to
two orders smaller.

## 7a. Scale, digestibility and review

The size of the library is the main driver of every cost measured here, so it is worth stating
plainly.

- **Size:** `OAI` is 122,458 AI-generated Lean files and 26.06 million lines (1.57 GB of source).
  Mathlib is 9,112 files and 2.42 million lines. `OAI` is about 11 times the size of Mathlib.
- **Reading cost:** at 1,000 lines an hour and 2,000 working hours a year, reading the 26 million
  lines once would take about 13 person-years, before any attempt to understand them.
- **Review:** Mathlib's contents entered through pull requests with review and maintainer approval
  over nearly a decade (772 contributors on its statistics page). No comparable review process is
  described for `OAI`; the repository's README says its results are at different stages of
  verification and that some of the unformalized ones could have issues.
- **Cost of checking everything** (measured here, section 1a): 3.8 days of wall time on a
  thermally limited laptop (13.8 hours of building on one 32-vCPU cloud machine), 150 to 200 GB of disk with archiving of the generated build files (about
  700 GB without), up to 26 GiB of memory for a single Comparator check, and a mapping budget that
  the Linux default covers only for modules below about 13,100 imported module-system modules.
- **Routine use is far cheaper than the whole.** A user of one result needs only the transitive
  import closure of the modules involved, not the library. Across the 416 configurations the in-repo
  closure of the solution module has a median of 77 modules (0.07% of the 107,978-module union), a
  75th percentile of 300, a 90th percentile of 735 and a maximum of 4,774. Of the 416 configurations,
  the 230 with closures under 100 modules took a median of 4 minutes to check (90th percentile 10
  minutes); the 74 with 501 or more modules took a median of 6 to 15 minutes by size class, with
  maxima of 10.9 hours and 4.7 hours. Building a closure is slower
  than checking it (`HeckeSevenEighths`, 2,925 modules, built in about 55 minutes and checked in 9
  minutes under load). The full-library costs matter mainly for independent reproduction, for
  maintainers, and for anyone assessing the collection as a whole. Even a one-module configuration
  pays the mapping cost of Mathlib (about 54k in the checker), so the mapping budget is a Mathlib
  effect, not a library-size effect.

Two recent essays note the same general worry about formalization versus understanding in
mathematics.

- Terence Tao, thread of four posts, 2026-10-06 (https://mathstodon.xyz/@tao/117395267721642920): in
  traditional mathematics a breakthrough proof is digested through talks, workshops, collaborations
  and eventually textbooks; when open problems are instead solved autonomously by AI prompters who
  do not engage with the field, that follow-on activity does not happen, and solutions are
  "harvested at large scale in an unsustainable fashion". He argues the community should value
  progress more holistically, "for instance by elevating the role of exposition, but also that of
  community building and opening up new directions of study", and believes AI can help with those
  too.
- David Bessis, "The fall of the theorem economy"
  (https://davidbessis.substack.com/p/the-fall-of-the-theorem-economy): argues that AI could produce
  correct theorems and formal proofs while mathematics loses what makes it valuable, which is
  understanding that spreads through a community; he quotes Thurston ("The product of mathematics is
  clarity and understanding. Not theorems, by themselves.") and says that even correct
  unintelligible proofs are not accretive to the mathematical corpus.

## 8. Not done yet

- The cause in nanoda of the non-terminating reduction: the term that triggers it is not identified, and only two of the six failing groups have a backtrace (nanoda_lib issue 55).
- Per-declaration Lean-kernel times to join with nanoda's, and a Lean replay time for the 18 long configurations measured the same way as the paired sweep.
- Nanoda on `Catalan`, `UniqueGamesTheorem` and `DirectedFeedback` with the fix, when there is one, and on the other failing groups.
- The `MMAP=OFF` toolchain build, the `GLIBC_TUNABLES` comparison, repeated trials for variance.
- Proposed upstream README patch: state that building the aggregate target `OAI` needs `vm.max_map_count` of at least 150,000 (measured need: 148,940;
  262,144 leaves a margin), that the per-area libraries build at the Ubuntu default of 65530, and that the `MMAP=OFF` workaround is only needed when
  the limit cannot be raised.
