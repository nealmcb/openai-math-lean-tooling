# Could the `let` patch make nanoda accept what it should reject?

The patch (`tools/patches/nanoda-let-fvar.patch` against 8199c74; rebased onto master
37cb87b7e6 together with the `Nat.succ` guard in
`tools/patches/nanoda-let-fvar-and-succ-guard-37cb87b.patch`) changes one typing rule and adds
one reduction. This note gives the argument that neither can make nanoda accept an ill-typed
term, the places where the argument depends on implementation details, and the tests that check
them.

## What changed

Stock nanoda types `let x : A := v; b` by checking `A` is a type and `v : A` (in Check mode), then
inferring the type of `b[v/x]`, the body with the value substituted.

Patched nanoda does the same checks, then creates a fresh free variable `x` (a `Local` with a
unique id, of type `A`), records `x ↦ v` in `TcCache::let_vals`, infers the type `T` of `b[x]`,
and returns `T[v/x]` (`abstr` then `inst`). During that inference `whnf` replaces `x` by `v` when
`x` is the head of the term being reduced (the new arm in `whnf_no_unfolding_aux`).

This is the rule of Lean's kernel (`infer_let` in `src/kernel/type_checker.cpp`: check the type
and the value, extend the local context with a let-declaration, infer the body, zeta-unfold the
variable in `whnf_core`). Lean returns the body's type with the let kept or dropped; nanoda
substitutes the value, which is definitionally the same.

## Why it cannot accept more than stock nanoda

Everything the patched checker concludes about the body it concludes in a context where `x`
stands for `v`. Two facts make that safe:

1. **The checks before the body are unchanged.** `A` must be a sort and `v`'s type must be
   definitionally equal to `A` (Check mode), exactly as before. So `x : A` with `x ≡ v` is a
   context that stock nanoda's substitution also justifies.
2. **The only new conversion is `x ≡ v`, which holds.** Any judgement about `b[x]` that uses
   unfolding of `x` is a judgement about `b[v/x]` with some occurrences not yet substituted. Where
   `x` is not unfolded (it is not at the head, or a check skips terms with free variables, such as
   the `Nat` literal shortcuts and the `Nat.succ` guard), `x` is an opaque variable, and treating
   a defined term as an unknown one can only make a check fail, never succeed. So the patch can
   lose completeness (reject something stock accepts) but not soundness, provided `x` always
   means `v`.

"`x` always means `v`" is where the implementation matters:

- **Identity.** `x` is made by `mk_unique`, a per-declaration counter, so two lets never share a
  variable even when they have the same name and type (siblings, shadowing, two declarations).
  Caches keyed by expression (`infer_cache`, `whnf_cache`, `eq_cache`, `defeq_fail_cache`) then
  never mix two lets. A key built from name and type alone (as de Bruijn levels would be) would
  be unsound; the M2 mutant below shows the tests catch that.
- **Lifetime.** `let_vals` lives as long as the `TypeChecker`, which is created per declaration,
  so nothing carries over between declarations. Inductive checking clears the whole `TcCache`,
  `let_vals` included; if that ever happened inside a let body, `x` would become opaque (a
  rejection, not an acceptance).
- **Escape.** The returned type has `x` replaced by `v`, so `x` does not leave the `let`. Even if
  it did, it would keep its value for the rest of the declaration.
- **Counter overflow.** `unique_counter` is a `u32` incremented without a check; after 2^32
  unique variables in one declaration an id would repeat. That needs billions of allocated
  expressions in one declaration, and the counter was already used for inductive and quotient
  locals; a `checked_add` would remove the question.
- **Infer-only mode** does not check `v : A`, as before and as in Lean (`infer_only`). Infer-only
  is used on terms already checked; in the patched rule an occurrence of `x` gets type `A` rather
  than the type of `v`, which differs only if `v : A` was never checked.

The `Nat.succ` guard (`tools/patches/nanoda-succ-fvars-guard.patch`) only removes a reduction
when the argument has free variables, so it can only cause rejections.

## Tests

`tools/nanoda_let_tests.py` exports the theorems in `tools/nanoda_let_tests/LetTests.lean` and
runs each nanoda build on the well-typed export (must accept) and on 11 exports that each contain
one ill-typed declaration (must fail an assertion, exit 101):

| variant | what is wrong | what it exercises |
|---|---|---|
| `let_pos1_bad` | `(let x := 2; x + 1) = 4` | substitution into arithmetic |
| `let_sib_bad`, `let_shadow_bad` | the second / inner of two same-name, same-type lets compared with the first one's value | identity of lets |
| `let_func_bad` | `(let f := fun y => y + 1; f 2) = 4` | a let-bound function applied |
| `let_under_binder_bad` | `∀ z, (let x := z + 1; x) = z + 2` | a value with an outer bound variable |
| `let_fin_bad`, `let_in_type_bad` | wrong bound / wrong `Fin` | dependent types, a let inside a type |
| `let_xd2_bad` | a second declaration with the same let shape, wrong value | nothing carried over between declarations |
| `let_sibv_value`, `let_shadowv_value` | a proof that type-checks only with value 55 or 66, given value 1 | the value lookup during inference |
| `value_type` | a `Nat` let given a `Bool` value that nothing else uses | the check of the value against the annotation |

The first eight, built by giving a correct proof a false statement, compare statements by
substitution and would pass even if the value lookup were wrong; the last three are export edits
that only the new code paths can catch. The script first prints how many let nodes each theorem
contains (lean4export shares nodes regardless of binder names, which once merged two test lets).

To check that the tests can fail, two deliberately broken versions of the patch were built:
M1 drops the value-against-annotation check, M2 keys values by name and type (first binding wins)
(`tools/patches/nanoda-let-mutant-M1.patch` and `-M2.patch`, to apply on top of the patched tree).
Results 2026-10-25 (`results/nanoda-let-tests-2026-10-25.txt`):

| build | result |
|---|---|
| master 37cb87b, stock and patched | 12/12 |
| 8199c74, stock and patched (the build of the 416-configuration sweep) | 12/12 |
| M1 | accepts `value_type` |
| M2 | accepts `let_sibv_value` and `let_shadowv_value` |

`cargo test --release` passes (54 tests) on stock and patched builds of both commits.

## What the sweep does and does not show

The 416 configurations are all accepted by Lean's kernel, and patched nanoda accepted every one
that stock accepted plus 7 more. That is evidence about completeness and speed; since every input
is a valid proof, it says nothing about soundness. The argument and the negative tests above are
the soundness evidence.
