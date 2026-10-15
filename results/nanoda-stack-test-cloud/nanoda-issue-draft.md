# Posted 2026-10-15 as https://github.com/ammkrn/nanoda_lib/issues/55 (text as posted, apart from later edits on GitHub)

Title: Stack overflow, then "index exceeds 31-bit capacity" panic, in `whnf` / `try_reduce_nat` on a small set of declarations that Lean's kernel checks in seconds

## Summary

Running nanoda on exports of the openai/math library (Lean 4.34.1, https://github.com/openai/math at commit fd4aeeb2ee4fc729c18d98444fed42fd0529eeeb) it accepts almost everything, and at 4 to 6 times the speed of Lean's own replay. A handful of declarations never finish: nanoda aborts with a stack overflow, or with a much larger stack runs for half an hour to 260 to 285 GiB and then panics with `index 2147483648 exceeds 31-bit capacity` (`src/util.rs:55`). A 7.7 MB export of one such theorem reproduces the stack overflow in about a second. A gdb backtrace of two different failing declarations shows the same pattern: `TypeChecker::whnf` and `TypeChecker::try_reduce_nat` alternating hundreds of thousands of times, so the failure looks like a reduction that does not make progress, not a deep but finite term and not just a too small stack. Lean's kernel accepts every one of these declarations.

## Overall picture

Exports made with lean4export 076e8e5 and the target list Comparator passes (the theorem, the Quot declarations, the permitted axioms and the primitives), checked with nanoda_lib 3a24072 (v0.4.19), `nat_extension` and `string_extension` on.

- 416 solution configurations (each the export of one theorem and everything it depends on, 18 MB to 3.9 GB): nanoda accepts 401. Compared with Lean's `Environment.replay` on the same export (4 threads for nanoda), the median time ratio over 380 configurations is 0.21 (nanoda is about 5 times faster), and the total over those is 2.75 hours against 10.3 hours.
- The 14,481 library modules that no solution imports, exported in batches (about 437,000 named declarations, plus auxiliary proofs): 76 of 77 batches or batch pieces are accepted, the failing one being the Problem355 declaration below.
- Every failure is a small group of declarations; all dependencies of those declarations check normally.

## Declarations that do not finish

Each of these begins in the per-declaration log (I added start and end lines for every declaration) and never ends.

| Group | Declarations that never finish |
|---|---|
| RoundTables (8 configurations) | `...Foundations.PCP.RoundTables.sizeFactor_positive`, `...build_size_le` |
| Catalan | `OAI.InternalCatalan.fixedDeterminantPrimeCutoff_ge_260`, `...fixedDeterminants_residue_ne_zero_of_lt` |
| Problem355 | `OAI.Problem355.MainDigitLaw.sampled_orbit_det_gt` |
| Laughlin, LaughlinPlanar | `OAI.Laughlin.Certificate.computeLDL_21_*_*._proof_1_1` |
| LaughlinFock | `OAI.LaughlinFock.fourLDLChecked_*._proof_1_1` |
| KMedianThreshold | `OAI.MetricKMedian.PCP.Compiler.CloudSpec.padding_code` |
| SquareDifference | `OAI.SquareDifference.tupleEta_le`, `tupleSubLaw_full`, `tupleLaw_decomposition`, `tupleGoodLaw_probability` |
| ContinuumCoulombHardness | `OAI.ContinuumCoulomb.QuantumRawExchange.budgetProgram`, `matrixBudgetProgram` |

The RoundTables group is DirectedFeedback, UniqueGamesTheorem, BinPackingGap, VertexCover, IndependentSets, MinUncut, PerfectCompleteness and OptimalMaxCut; each has its own generated copy of the same code in its namespace. How each one fails:

- DirectedFeedback and UniqueGamesTheorem: stack overflow at 16 MiB and at 1 GiB; with a 16 GiB stack (UniqueGamesTheorem) 1,874 s, 285 GiB, then the 31-bit panic.
- The other six RoundTables configurations: nanoda exits with an error after 30 to 60 s at a 1 GiB stack, the same two declarations unfinished (no backtraces taken).
- Catalan: 31-bit panic after 2,014 s and 259 GiB.
- Problem355: stack overflow of a worker thread after 488 s and 35 GiB, with a 1 GiB stack.
- Laughlin: killed at 151 GiB. LaughlinPlanar: reached 175 GiB, was suspended there and ended by a 4 hour timeout. LaughlinFock: abort at 127 GiB.
- KMedianThreshold, SquareDifference, ContinuumCoulombHardness: nanoda exits with an error, declarations unfinished (no backtraces taken).

For the Laughlin, KMedianThreshold, SquareDifference and ContinuumCoulombHardness groups I have the unfinished declarations from the per-declaration log but have not taken a backtrace, so I do not know that they are the same loop. The first, second and third rows are the ones analysed below.

## Reproduction (small, about a second)

Attached: `sizeFactor_positive.export.xz` (0.8 MB, 7.7 MB uncompressed) and `nanoda-config.json` (the config Comparator writes, `num_threads: 4`).

    git clone https://github.com/ammkrn/nanoda_lib && cd nanoda_lib && git checkout 3a2407216ee84a75f9e1aead6803d0578be06ae7
    cargo build --release
    xz -dk sizeFactor_positive.export.xz
    target/release/nanoda_bin nanoda-config.json

Observed (exit 134, SIGABRT):

    thread 'thread_0' has overflowed its stack
    fatal runtime error: stack overflow, aborting

The export is of `OAI.DFVSGames.Foundations.PCP.RoundTables.sizeFactor_positive` in the DirectedFeedback formalization; the README next to the export has the exact lean4export command.

## Where it overflows (gdb)

Two different failing declarations give the same picture.

1. `sizeFactor_positive`, the 7.7 MB export above, run with `num_threads: 1` under gdb and stopped at the SIGSEGV: the stack is 116,000 frames deep, `TypeChecker::whnf` and `TypeChecker::try_reduce_nat` alternating 58,000 times each, with `check_declar -> infer -> def_eq -> whnf_no_unfolding_aux` at the bottom.
2. `OAI.Problem355.MainDigitLaw.sampled_orbit_det_gt`, an export of that one declaration (247 MB, all 35,715 of its dependencies check normally), run with 8 threads and a 256 MiB checker stack: 1,864,067 frames, 932,010 of `whnf` and 932,007 of `try_reduce_nat`, the remainder a few `def_eq`, `whnf_no_unfolding_aux`, `inst_aux` and `infer` frames below `check_declar`.

        #36 TypeChecker::whnf
        #37 TypeChecker::try_reduce_nat
        #38 TypeChecker::whnf
        #39 TypeChecker::try_reduce_nat
        ...

`try_reduce_nat` calls `self.whnf` on its argument (the `Nat.succ` case, and `do_nat_bin` for the binary operations), and `whnf` calls `try_reduce_nat` again. A deeper stack only gives a deeper recursion, and the exports are far too small to contain terms millions of levels deep, so this is a reduction that does not terminate or that expands a numeral one step at a time without sharing (for example a symbolic `Nat.add x n` with a huge literal `n`). An experiment that peeled chains of `Nat.succ` in a loop inside `try_reduce_nat` did not remove the problem: the check ran 59 s before overflowing, with the same two functions alternating. I have not identified the offending term.

## Larger stacks and the 31-bit limit

The checker threads use `.stack_size(crate::STACK_SIZE)`, a constant of 16 MiB. I made it settable (an environment variable, otherwise unchanged) and logged the start and end of each declaration. Full-configuration exports on a 512 GiB machine, 64 threads, no time or memory limit:

| Export | Stack | Outcome | Wall | CPU | Peak memory |
|---|---|---|---|---|---|
| DirectedFeedback (753 MB) | 1 GiB | stack overflow, abort | 131 s | 373 s | 24.6 GiB |
| UniqueGamesTheorem (682 MB) | 1 GiB | stack overflow, abort | 131 s | 363 s | 25.1 GiB |
| UniqueGamesTheorem | 16 GiB | panic: `index 2147483648 exceeds 31-bit capacity` | 1,874 s | 3,791 s | 285 GiB |
| Catalan (833 MB) | 1 GiB | panic: `index 2147483648 exceeds 31-bit capacity` (`src/util.rs:55`) | 2,014 s | 6,238 s | 259 GiB |

The panic shows `Ptr::from` in `src/util.rs`: the temporary (TcCtx) dag grew past 2^31 entries while checking the unfinished declarations.

## The main thread has a separate stack limit

On the 247 MB export of `sampled_orbit_det_gt`, even with the checker stack set to 1 GiB, the process aborts after 35 s and 0.5 GiB with `thread 'main' has overflowed its stack`, before any declaration has finished. With `ulimit -s unlimited` it gets past this, checks the 35,715 dependencies, and then fails in a worker thread as described above. I did not find which part of the main thread recurses (reading the export or building its dependency order); the export has 247 MB of lines and a few very deeply nested expressions would explain it. Running the main work on a thread with a configurable stack, as for the checker threads, would remove this limit.

## Lean's kernel on the same inputs

Comparator's built-in replay (`Environment.replay` on the same export) accepts every one of these configurations. For example the complete Comparator check, including the export, takes 194 s (UniqueGamesTheorem), 267 s (DirectedFeedback) and 2,246 s (Catalan) on a laptop, at 6 to 7 GiB of memory.

## Notes

- Nanoda is much faster than Lean's replay on the large majority of declarations: the median ratio is 0.21 at 4 threads, and the scaling to 64 threads is close to linear on large exports (for example a 3.85 GB export in 672 s). One configuration (ArnoldCounterexample) was 3.7 times slower than Lean's replay and one (PartitionPrinciple) 1.9 times slower, so there may also be a slow path there.
- Comparator reports the abort as "nanoda kernel rejected the solution" (exit 134), which reads as a verdict on the proof. A check that fails with a panic or an abort could be reported differently.
- The Lean Kernel Arena reports every failure as a rejection too, so a crash like this may not be visible there.
- A missing export file gives `Error: Failed to open export file: Os { code: 2, kind: NotFound, ... }` (`src/util.rs:997`) without the path, which is hard to diagnose when the path is relative and comes from a config file; including the path in the message would help.
- Suggestions: a recursion or size guard that returns an error instead of aborting; a configurable stack size for the main thread as well as the checker threads; and possibly a cap on the temporary dag with a clear message. It may also be worth looking at what the Lean kernel does differently for these declarations (caching, lazy delta reduction, or natural-number literal handling).

Versions: nanoda_lib 3a24072 (v0.4.19), rustc 1.92 nightly, Ubuntu 22.04 and 24.04, Lean 4.34.1, lean4export 076e8e5, Comparator d03acab.
