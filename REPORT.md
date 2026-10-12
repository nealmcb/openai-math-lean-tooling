# Report: can the default Linux memory mapping limit verify OpenAI/math Lean?

Status as of 2026-10-10 15:10 MDT (local workstation only, no cloud spend; the Comparator run is
still in progress). Repo pinned at openai/math commit fd4aeeb2ee4fc729c18d98444fed42fd0529eeeb, Lean
v4.34.1, Mathlib d13f23b723b8a846827a245b89c10fc7d3f11612. Raw data is under results/.

## 1. Bottom line

- On Ubuntu 22.04.5 (hardware-enablement kernel 6.8, `vm.max_map_count` = 65530) every build and
  Comparator check run so far succeeded at the default limit. 38,442 of the 107,978 modules in the
  Comparator solution closure are built (35.6%; 39,209 of 122,458 OAI files, 32.0%), including the
  deepest non-root module `OAI.Combinatorics.Progressions.Main`. The highest sampled single-process
  count was 58,559 (89% of the limit).
- The one module predicted to fail at 65530 is the root `OAI.lean` (about 143k mappings, 149k before
  calibration, from the whole-library model in section 3a; not measured). No other module is
  predicted above 61,124. The failure mode itself was reproduced with a file importing Mathlib plus
  9,272 built OAI modules: it fails at 65530 with `failed to read file ...olean` and succeeds at
  262144.
- About a third of the library has been compiled. The rest is untested, so "the default is enough
  for everything except the root" is a prediction (calibrated against 13 measurements, section 3a),
  not a result.
- Comparator has accepted 27 of the 416 configurations and rejected none, including the three
  L-function headline results (section 3c). Four deliberately wrong solutions (a `sorry`, an extra
  axiom, `native_decide`, a mismatched statement) were all rejected. What an acceptance does and
  does not establish is in section 5. Nothing in this report validates the manuscripts' mathematics.

## 1a. Resource estimates for the full run (this hardware)

Rough estimates for building every module and running Comparator on all 416 configurations,
extrapolated from this run's measured pace. Treat each as plus or minus 50%.

| Resource | Estimate | Basis |
|---|---|---|
| Wall-clock time, everything | about 3 days in total, about 1.5 to 2 days of it still to go | 38,442 of 107,978 modules built after about 22 hours of active running; checks add on top |
| Compiling (108k modules) | about 60 hours in total, about 40 remaining | measured 1,750 to 1,900 modules per hour with all 16 threads busy |
| Comparator checks (416) | about 12 to 20 hours of wall time with 3 in parallel, mostly overlapping the builds | 27 done: median 287 s, mean 1,410 s; small ones about 2 to 3 minutes, large ones 10 to 40 minutes; one outlier (`MUBSix`) took 4.7 hours, and a few more like it would add hours |
| Disk, working set | about 150 to 200 GB | `.olean` and related outputs 0.75 to 1 MB per module (80 to 105 GB), about 25 GB of compressed C archives, about 10 GB of dependency checkouts and tools, plus up to about 35 GB of uncompressed C for the batch in progress |
| Disk, if the generated C is kept | about 700 GB | 5.8 MB of C per module over 108k modules; it compresses to about 4% |
| Memory, build | about 20 to 30 GiB of real memory at full speed | lowest available memory seen during three big builds: 17 to 25 GiB of 60 (from about 45 idle); up to 17 processes at once; one Lean process reached 10.5 GiB |
| Memory, checks | typically 6.5 GiB; up to 26.1 GiB | 12 monitored checks; `MUBSix` 26.1 GiB, `ErdosReciprocal` 14.3 GiB |
| Memory, recommended | 64 GiB | tested only on 60 GiB with 39 GiB of swap; the run used up to 18 GiB of swap, so about 32 GiB would likely mean much slower or failed runs when a large check and a build overlap (not tested) |
| Mapping limit | the default 65,530 for everything except the root `OAI.lean`, which needs roughly 150,000 or more | section 3a |

**Hardware used:** a Framework Laptop 13 (13th Gen Intel Core) with a Core i5-1340P: 4 performance
cores with hyper-threading (up to 4.6 GHz) plus 8 efficiency cores (up to 3.4 GHz), so 12 physical
cores and 16 hardware threads, 60 GiB RAM, 39 GiB swap, a 2 TB WD Black SN850X NVMe drive (ext4),
Ubuntu 22.04.5 with kernel 6.8, on AC power. Under load the CPU package sat at its 100 C thermal
limit (load 20 to 30), so sustained speed was well below the chip's peak. A desktop CPU with real
cooling would probably finish sooner; that was not measured.

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

Every Comparator configuration run so far (27) built and checked at 65530; per-configuration numbers
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
  than the Ubuntu default; 262,144 would be ample. Not measured.

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

## 3c. Comparator results so far (27 of 416 configurations, 2026-10-10 15:10)

All 27 accepted, none rejected. Table: `results/cmp-all/configs.csv` (one row per configuration,
written by `tools/export_results.py`).

- **Which:** the three L-function headline configurations (`QuasiRiemannHypothesis`, which is the
  Comparator README's example command, `DirichletSevenEighths`, `HeckeSevenEighths`), the deepest
  module (`ErdosReciprocal`), `OstmannPrimes`, `OstmannComplete`, `MUBSix`, `PattersonFirstMoment`
  (the largest family outside `OAI.lean`), `KoebeCircleDomains`, `PolycyclicRecognition`,
  `StrongKadisonKastler`, and 16 small ones. The run goes largest first, then smallest to largest.
- **Check time** (active time, excluding pauses, for the snapshot of 27 configurations): median 287
  s. The slowest are `MUBSix` 16,981 s (4.7 h, 26.1 GiB), `StrongKadisonKastler` 2,914 s,
  `ErdosReciprocal` 2,472 s, `OstmannPrimes` 2,045 s and `DirichletSevenEighths` 1,660 s. The raw
  wall-clock values for `StrongKadisonKastler` (5,351 s) and `DirichletSevenEighths` (3,839 s)
  included 2,437 s and 2,179 s of manual pauses; `DirichletSevenEighths` is still about three times
  its siblings (555 to 564 s), for a reason that was not investigated. Check time is not predicted
  by closure size: `MUBSix` (3,381 modules) took 4.7 h and `OstmannComplete` (3,207) took 307 s.
  Later in the run the slowest checks were `TriangularEnergy` (5,713 s), `TriangularGaussian` (5,378
  s), `AtomicGaussian` (5,336 s) and `SKRatio` (4,154 s).
- **Pauses.** The run was frozen by hand five times (all logged in `driver.log` by `tools/pause.sh`
  and `tools/resume.sh`): 457 s, 345 s and 1,377 s on 2026-10-10 morning, 2,437 s that afternoon,
  and 4,882 s on 2026-10-11, 9,498 s (2.6 hours) in all. Raw records are left as measured;
  `tools/pauses.py` computes how much of any interval a pause covered, and `configs.csv` has
  `check_paused_s`, `check_active_s`, `build_paused_s` and `build_active_s` (and `build_share_s` is
  computed from the active build time). Of the 315 accepted configurations, two checks and one build
  overlapped a pause: the `KoebeCircleDomains` build is 2,204 s active (4,383 s raw), and the two
  checks above. The 16 compile-time artifacts in `module-times.csv.gz` (section above) come from the
  same pauses.
- **Check memory:** up to 26.1 GiB (`MUBSix`), 14.3 GiB (`ErdosReciprocal`), about 6.5 GiB for small
  ones. Measured for the 12 configurations run after the monitor was fixed.
- **Mapping counts in checks:** about 53.8k for any configuration, because the exporter imports
  Mathlib regardless of the solution; 56.4k to 58.6k for the deep ones. These agree with the model
  (section 3a).
- **Second kernel:** `TraceIdealTransportSupport`, one of the two nanoda-enabled configurations, was
  accepted by both Lean's kernel and nanoda. Its first run failed only because the nanoda binary was
  missing; Comparator printed "nanoda kernel rejected the solution" in that case, which is
  misleading. The other nanoda-enabled configuration has not run yet.
- **Build parallelism** (computed by `tools/parallelism_profile.py`): for the whole remaining build
  the average number of runnable modules is about 81, more than the 16 threads; for any single
  configuration it is 1 to 5, so configurations are built in batches to keep the cores busy.
- **Reading the build times.** `build_wall_s` in `configs.csv` is the time of the build step, not
  the cost of the configuration. It is near zero (7 to 10 s) when the configuration's modules were
  already compiled for an earlier configuration or batch, and for configurations built in a batch it
  repeats the whole batch's time on every row, so it is not additive: among the 191 configurations
  accepted at the time of this check the median batch held 12 configurations, the rows sum to 70.5
  hours, but the batch times divided among their configurations (the `build_share_s` column) sum to
  18.0 hours. The columns `batch_configs` and `modules_compiled_in_this_build` show which case
  applies. Real compile cost is better read from the per-module data below. Check times
  (`check_wall_s`) are per configuration and not shared.
- **Per-module data.** `results/module-times.csv.gz` has one row for each of the 69,182 modules with
  a recorded compile at the last export (the statistics below are from an earlier export of about
  48,200) with a recorded compile in the raw Lake logs (which are too bulky to keep in git): area,
  first compile time in seconds, number of compiles (3 modules were compiled more than once), source
  size, in-repo closure size and predicted mapping count. The times are wall-clock under load, so
  they are upper bounds on isolated compile time; they sum to about 260 module-hours, which divided
  by the 16 concurrent threads is a lower bound of roughly 16 hours of wall time. Modules that were
  only replayed from cache have no row. Per-module mapping counts were not recorded; only
  per-process peaks were, and the predicted counts are in `results/predicted-vmas.jsonl`.
- **How much module compile times vary** (an export of about 48,200 modules,
  `results/module-times.csv.gz`; wall-clock under load, so upper bounds). A lot, with a heavy tail:
  the median is 12 s, the 90th percentile 29 s, the 99th 181 s, the 99.9th 680 s and the maximum
  1,652 s. A third of the modules take under 10 s and 90% under 30 s, yet the slowest 1% (481
  modules) account for 17% of all compile time and the slowest 10% for 45%. Source size explains
  only part of it: on a log-log fit the slope is 0.45 and r-squared 0.39, and even at similar size
  the 10th to 90th percentile spread is 2 to 3 times (median 10 s at 1 to 2 KB of source, 17 s at 8
  to 16 KB, 36 s at 32 to 64 KB, 162 s at 128 to 256 KB). The two slowest real modules are single
  enormous files: `OAI.Analysis.NuclearUltrapower.SOSResidual` (993 KB of source, 1,652 s) and
  `OAI.Topology.EilenbergGanea.SeedContraction` (427 KB, 1,600 s). By area, `OAI.Analysis` is 41% of
  all recorded compile time (107 of 261 module-hours) from 23% of the modules, averaging 35 s a
  module against 11 s for the 14,141 `OAI.NumberTheory` modules (44 hours). Sixteen small
  `OAI.Analysis` modules show about 1,390 s each only because they were mid-compile during a
  23-minute manual pause, and ten more modules in the later export show about 4,900 s because of the
  81-minute pause on 2026-10-11 (26 are flagged in the file as `likely_pause_artifact`); they would
  otherwise head the slowest list, and shorter pauses left smaller traces that cannot be separated
  from real durations. The practical reading is that total build time is dominated by a small
  fraction of heavy modules, and that the critical path, not the average, decides how long a
  particular result takes.
- **Timing caveats:** the machine is a Framework 13 laptop with a Core i5-1340P (4 performance cores
  with hyper-threading plus 8 efficiency cores, 16 threads), running at its 100 C thermal limit
  during builds (load 20 to 30). Other work ran at the same time and the run was paused by hand at
  times, so times are indicative, not benchmarks. Mapping counts are unaffected.

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
main claim ("headline") as opposed to a supporting lemma. Level 3 is outside what machines check,
and level 4 is outside what this project addresses.

**Scope of a Comparator run.** The challenge files import little; each config names a separate
`solution_module` (for example `OAI.GroupTheory.ArtinCAT0.Main`) that the challenge file does not
import. Across the 416 configs (413 distinct solution modules), the combined import closure of the
solution modules is **107,978 modules (23.4 M lines)**, of which 38,442 (35.6%) are built at the
time of writing. Level-2 verification of everything therefore needs about as much as a full build,
and more than `lake build OAI` covers (91,762).

## 6. Can a full build fit on this machine?

Free space on the test machine's `/home` was 124.7 GB before the work started and stayed between 37
and 82 GB during the Comparator run.

| Item | Per module | If 108k modules |
|---|---|---|
| generated C (`.lake/build/ir`) | about 5.4 MB | about 580 GB |
| `.olean` plus `.ilean` and hashes (`.lake/build/lib/lean`) | about 1 MB | about 105 GB |

- The C files are an output Lake tracks: moving one away made Lake rebuild that module (3.6 s) when
  asked again, without rebuilding its dependents. Deleting C files as each batch finishes saves disk
  but means a later plain `lake build` will recompile those modules; checks that read the `.olean`
  files directly are unaffected.
- Compression: C files compress to 4.3% with gzip and 2.8% with xz (300-file sample), so about 580
  GB of C would be about 25 GB, but only on a compressing filesystem (this one is plain ext4) or as
  an archive at rest. `.olean` files compress to 33% (gzip) and 24% (xz), `.ilean` to 12%; but
  `.olean` files are memory-mapped at run time, so they must be stored uncompressed while in use. At
  rest an olean archive of 105 GB would be about 30 GB.
- Measured pace: the built count went from 24,430 to 38,442 modules in 7.4 hours (about 1,900 per
  hour, including pauses). At that pace the remaining 69.5k modules need roughly 37 hours; the
  deepest chains were built first, so the rest may go faster, but the heaviest checks are
  unpredictable.
- What worked: each batch's generated C is compressed (verified), removed after its checks, and
  restored for later builds, so disk never ran out. The `.olean` files (about 105 GB for the full
  closure) must stay uncompressed; the root `OAI.lean` additionally needs them all present at once.
  The cloud alternative (16 vCPU, 600+ GB, about a day) has not been used; candidate providers are
  DigitalOcean, AWS, Google Cloud and Hetzner.

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
- **Cost of checking everything** (measured here, section 1a): about three days of compute on a
  thermally limited laptop, 150 to 200 GB of disk with archiving of generated C (about 700 GB
  without), up to 26 GiB of memory for a single Comparator check, and a mapping budget that the
  Linux default covers only for modules below about 13,100 imported module-system modules.
- **Routine use is far cheaper than the whole.** A user of one result needs only the transitive
  import closure of the modules involved, not the library. Across the 416 configurations the in-repo
  closure of the solution module has a median of 77 modules (0.07% of the 107,978-module union), a
  75th percentile of 300, a 90th percentile of 735 and a maximum of 4,774. Of the 40 configurations
  accepted when this was written, the 25 under 100 modules took a median of 147 s to check; the 14
  with 1,000 or more modules took a median of 978 s (maximum 16,981 s). Building a closure is slower
  than checking it (the headline `HeckeSevenEighths`, 2,925 modules, built in about 55 minutes and
  checked in 9 minutes under load). The full-library costs matter mainly for independent
  reproduction, for maintainers, and for anyone assessing the collection as a whole. Even a
  one-module configuration pays the mapping cost of Mathlib (about 54k in the checker), so the
  mapping budget is a Mathlib effect, not a library-size effect.

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

- The remaining 389 Comparator configurations (and the second nanoda-enabled one).
- The root `OAI.lean` measurement and the full library build.
- The `MMAP=OFF` toolchain build, the `GLIBC_TUNABLES` comparison, repeated trials for variance.
- A cloud run (none was needed so far).
- Proposed upstream README patch (draft once the root measurement exists): state that building the
  aggregate target `OAI` needs `vm.max_map_count` of at least roughly 200,000 (measured value to
  replace this estimate), that the per-area libraries build at the Ubuntu default of 65530, and that
  the `MMAP=OFF` workaround is only needed when the limit cannot be raised.
