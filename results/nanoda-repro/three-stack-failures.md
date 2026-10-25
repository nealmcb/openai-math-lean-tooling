# Three configurations that overflow nanoda's stack on master 37cb87b7e6

ContingencyTables, LogspaceEquality and MatchingFPRAS are accepted by Lean's kernel and by nanoda
f67473b (16 MiB checker stack), and abort with a stack overflow (exit 134) on nanoda master
37cb87b7e6, with or without the `infer_let` and `Nat.succ` guard patches. With a 1 GiB stack master
accepts all three. Measured 2026-10-25 on the laptop, one checker thread.

## What recurses

gdb on a release build with line tables (`gdb-backtrace-lines.cmds`), MatchingFPRAS, master:
87,213 frames, of which 29,030 each of `whnf` (tc.rs:800) -> `try_reduce_nat` (tc.rs:443) ->
`do_nat_bin` (tc.rs:376, `self.whnf(x)`), i.e. `try_reduce_nat` evaluating the first operand of a
`Nat` binary operation, whose evaluation calls `try_reduce_nat` again.

Outermost frames: `check_declar` -> `infer` -> `infer_let` -> `infer_app` -> `def_eq` ->
`def_eq_binder_multi` (binders opened as free variables) -> `def_eq_app` -> `def_eq` ->
`lazy_delta_step` -> `delta` -> `whnf_no_unfolding_cheap_proj` -> `reduce_rec` (a recursor whose
major premise is a `Nat` comparison) -> `whnf` -> `try_reduce_nat`.

## The terms

An instrumented build (`tools/patches/nanoda-reduce-nat-depth-debug.patch`, against 37cb87b) keeps
the stack of terms passed to `try_reduce_nat` and reports it at depth 2000:

| configuration | declaration | the 2000 levels |
|---|---|---|
| MatchingFPRAS | `OAI.MatchingFPRAS.ExecutableEstimator.upperRealizer` | 1992 `Nat.add`, 2 `Nat.mul`, 2 `Nat.ble`, 2 `Nat.succ`, 1 `Nat.beq` |
| ContingencyTables | `OAI.ContingencyTables.CountingPositiveWordBound.measure_public` | 1995 `Nat.succ`, 2 `Nat.add`, 2 `Nat.mul` |
| LogspaceEquality | `OAI.ExactDerandomization.Vessel.Basket.Sack.Ground.advances._proof_1_2` | 1988 `Nat.add`, 7 `Nat.mul`, 3 `Nat.ble`, 1 `Nat.mod` |

In all three every level contains free variables (the declaration's or a lambda's binders, e.g.
`m n` in ContingencyTables, `q w h u s` in LogspaceEquality). The top is an arithmetic comparison,
e.g. in MatchingFPRAS `Nat.ble (Nat.succ (x * y)) z` with `x` a closed `TreeFraction` computation.
Below the first few levels every term is a step of the structural-recursion unfolding of
`Nat.add`/`Nat.mul` (`Nat.rec` over `Nat.below`, `Nat.mul._f`) on a literal: an operand with a free
variable is not a literal, so the GMP shortcut fails, `whnf` unfolds the definition one recursor
step, and `try_reduce_nat` then evaluates the next operand down. The chain is as long as the
literal: with a 1 GiB main-thread stack the nesting reaches between 65,536 and 131,071 levels in all
three (MatchingFPRAS: literal 98,008).

## Why f67473b passes

f67473b returned `None` from `try_reduce_nat` when the term had free variables; 6239144 (PR 58,
"remove vestigial has_fvars check") removed that. Here level 1 already has free variables, so the
old check stopped the chain before it started. Restoring the check for `Nat.succ` only (the issue 61
proposal) does not help, because these chains go through the binary operations. Restoring it for
the binary operations is equivalent to the whole old check (their free variables are their
operands'), which brings back issue 57.

## Lean

Lean 4.34.1's `whnf` calls `reduce_nat` without a free-variable check, and `reduce_bin_nat_op`
evaluates the first operand with `whnf`, the same shape as nanoda; only `lazy_delta_reduction`
guards `reduce_nat` with `!has_fvar`, and nanoda's `delta_try_nat` has the same guard. Lean's
replay (`replaytime`) accepts MatchingFPRAS in 73-78 s and 1.9 GB with `ulimit -s` 8 MB or 1 MB, but
the kernel runs on a non-main thread (main-thread stack stays at 136 kB, 4 threads), so this does
not show whether Lean nests as deep.

## Numbers (one thread)

| build | MatchingFPRAS | ContingencyTables | LogspaceEquality |
|---|---|---|---|
| master 37cb87b, 16 MiB (4 threads) | abort 6.3 s | abort | abort |
| master + debug patch, 1 GiB main stack | accept 62 s, 1.7 GB | accept 49 s, 1.7 GB | accept 70 s, 2.8 GB |
| f67473b, 16 MiB (4 threads) | accept 21 s, 0.6 GB | accept 18 s, 0.6 GB | accept 19 s, 0.8 GB |

Exports were made with `tools/nanoda_retest.py --keep` (scratch/retest/, 485, 493 and 441 MB).
