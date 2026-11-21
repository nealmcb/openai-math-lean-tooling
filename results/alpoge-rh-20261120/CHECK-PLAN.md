# Plan: an independent check of Alpöge's Lean proof of the Riemann hypothesis

**Status: a plan only, not run.** This was Claude's idea (2026-11-20). It runs only after Neal
approves it, including the cost cap below.

## What is being checked

Levent Alpöge announced on 2026-11-20 a proof of the Riemann hypothesis (RH), and of the
generalized RH for Dirichlet L-functions, found with Claude and published only as Lean code
(https://alpo.ge/remark.pdf; https://alpo.ge/lean.tar.gz.part01 … part14).
- Archive: 14 parts, 239 MB; sha256 of the joined parts
  `9631b4f020199e580ba86178cb56c6e9b09f690c2369a80dc4334aa93f49c7fc`. 175,187 `.lean` files, 0.98
  GB of source.
- Toolchain: Lean `v4.33.1`, Mathlib `0df444a360eaa60ab8c11dca51a86af692955474` (2026-08-21).
- Theorems (`lean/src/Main.lean`): `riemannHypothesis : RiemannHypothesis` (Mathlib's own
  definition, unchanged by the project), `riemannZeta_eq_zero_re`, `LFunction_ne_zero_of_half_lt_re`,
  `LFunction_eq_zero_re` and `LFunction_eq_zero_re_of_isPrimitive`, the last four over the
  propositions defined in `lean/src/Statements.lean`, which imports only Mathlib.
- Source scan (`tools/lean_source_scan.py`): no `sorry`, `axiom`, `native_decide`, `unsafe`,
  `implemented_by`/`extern`, `opaque` or `#eval`. Code that runs during the build: five `BuildAid`
  files that hide names from library suggestions, one `addDecl` copier
  (`Formalism/HermitianCurvature/HermitianCurvatureProofs/CutCptCopy.lean`), and a tactic
  `kexactB` that assigns proof terms without the elaborator's type check, leaving all of that
  checking to the kernel.

Already reported on Lean Zulip (2026-11-20): several people compiled it, and Andrew Sutherland ran
nanoda on a 61.57 GB export (sha256 `5ea74b91…244e`): accepted in 27 min 42 s on 80 threads, 9.2
CPU-hours, peak 89 GB. That nanoda is the one bundled with Lean 4.36.0, commit `4c544ed4`
(2026-09-09), 42 commits behind nanoda master `0da9f98fea`. The missing commits include soundness
hardening: projection type names (#48), restored nested field counts (#63), validation of restored
recursors (#65), Quot and temporary-name checks (#75) and parser validation. Comparator's paranoid
mode needs Lean 4.35 or later, so it was thought unavailable for a 4.33.1 project, and the project
has no challenge module.

## What this check adds

1. **A Mathlib-only challenge.** `Challenge.lean` imports only Mathlib and states the five theorems
   with `sorry`; the four propositions of `Statements.lean` are copied into it verbatim, and
   `riemannHypothesis` uses Mathlib's `RiemannHypothesis` directly. The judge then checks that each
   solution theorem proves exactly the challenge's statement, with only `propext`, `Quot.sound` and
   `Classical.choice`.
2. **Paranoid mode despite Lean 4.33.1.** Since Lean 4.35, Comparator is `lake comparator`, and it
   can judge exports made elsewhere (`--challenge-from-export`, `--solution-from-export`). So the
   project is built and exported with its own Lean 4.33.1 and judged by Lean `v4.37.0-rc1`'s
   `lake comparator --paranoid`, which runs Lean's kernel plus `leanchecker-paranoid`, `lean4lean`,
   `nanoda` (`8de7e0c4`, with the hardening above), `con-leche` and `con-ron`.
3. **Current nanoda.** `tools/nanoda_ab.py` on the solution export with the recommended build
   `master+71+guard.64M` (master `0da9f98fea` + PR 71 + the Nat.succ guard, 64 MiB stack) and plain
   `master`.
4. **Same object as Sutherland's.** If our export's sha256 equals his (full hash needed from the
   thread), both runs checked the identical file.
5. **A Lake cache of the build,** per this project's rule that compiles are preserved. Publishing it
   is a separate decision.

## Steps

All on one isolated spot instance: `tools/cloud_spot_scratch_launch.sh` (no IAM role, metadata
service off, no data volume, SSH only from the laptop), whose CloudWatch alarm stops it after 2 idle
hours (`tools/cloud_guard.sh`). Results are copied to the laptop with scp; no credentials ever reach
the machine.

| # | Step | Expected | Limit |
|---|---|---|---|
| 0 | Launch: r7a.8xlarge (32 vCPU, 256 GiB) or r6a.8xlarge, 450 GiB scratch | minutes | spot only |
| 1 | Download the 14 parts, check the sha256 above, unpack | 2 min | |
| 2 | `lake exe cache get` (Mathlib), then `lake build Main` | 10–16 h (estimate: ~470 CPU-h, scaled from openai/math) | 24 h |
| 3 | `tools/lake_cache_project.sh` on the build; copy bundles and mapping to the laptop | 30 min | |
| 4 | Solution export of the five theorems with `lean4export` `v4.33.0` (`15f6055e29`, the 4.33 line); sha256 | 20–40 min, ~62 GB | |
| 5 | Challenge: build `Challenge.lean` against the same Mathlib; export it | 10 min | |
| 6 | `lake comparator --paranoid` from Lean `v4.37.0-rc1`, both from exports; `bubblewrap` installed | unknown: nanoda ~30 min on 80 threads; `lean4lean`, `con-leche`, `con-ron` untimed at this size | 12 h, 200 GiB cap |
| 7 | `nanoda_ab.py`: `master+71+guard.64M`, then `master`; 32 threads | 1–2 h each | 4 h, 200 GiB cap each |
| 8 | Copy logs, hashes and results to `results/alpoge-rh-20261120/`; terminate after cancelling the spot request; `cloud_guard.sh sweep` | | |

Order: the build must come first. After it, the export (step 4) is the long pole for every checker.
Steps 6 and 7 each need about 90 GB, so they run one at a time on a 256 GiB machine.

**First thing to test, before the long runs:** whether Lean 4.37's `lake comparator` reads a
4.33-era export. If it does not, the fallback is standalone Comparator at the v4.33 line
(`leanprover/comparator` `3927ad383f`, toolchain bumped to 4.33.1) with Lean's kernel and our
nanoda builds, without the paranoid checkers.

**Spot reclaims:** the request is persistent with stop behaviour, so a reclaim keeps the disk and
Lake resumes the build. Each long step records its start and end in a log, so a resumed step is
visible as such.

## Cost

About 20–30 machine-hours at roughly $0.6–0.9/h on spot, plus about $1 of disk: **about $15–30.
Cap: $40**; the run stops and reports at the cap. The daily budget alert (`experiment-daily`,
$10/day) will fire during the run; that is expected.

## Records

`results/alpoge-rh-20261120/RUNS.md`: inputs and their hashes, each checker's exact build (commit,
sha256, configuration), times, memory, exit codes and full logs, in the form of
`results/yang-mills-20261028/RUNS.md`.
