# Checks of the openai/math update fd4aeeb2ee -> 7ef5c0cc5 (2026-10-27/28)

openai/math `7ef5c0cc5` (2026-10-26), Lean 4.34.1, Mathlib unchanged. 20 configurations are
affected (`impact.tsv`, from `tools/update_impact.py`); the other 396 are unchanged. Three are
new: HodgeConjectureCMAbelianVarieties/main, LocalSmoothing and SubexponentialSAT.

## nanoda builds

All are built from upstream nanoda_lib master `d0a02cc5de` (2026-10-27, the merge of PR 75) with
`tools/build_nanoda_variant.sh`; the descriptions are in `nanoda-builds/`. Records identify the
binary by `sha256`; records written after 2026-10-28 02:00 UTC also carry the description
(`build`) and the path of the full output (`log`, in `cloud/nanoda-logs/`).

| label | sha256 (first 12) | source |
|---|---|---|
| `master` | `c91a3d932721` | master as is (16 MiB checker stack) |
| `master+71` | `79e5ff1c272d` | master with PR 71 (`infer-let-local` at `19226226ad`) merged |
| `master.64M` | `76a3b6a383e6` | master, `STACK_SIZE` 64 MiB |
| `master+71.64M` | `8e2a3e8bc5c0` | master + PR 71, `STACK_SIZE` 64 MiB |
| `master+71+guard.64M` | `0043e9f736dc` | master + PR 71 + `tools/patches/nanoda-succ-fvars-guard.patch`, 64 MiB: the combination recommended in nanoda_lib issue 61 |

`master` and `master+71` ran on every configuration; the 64 MiB builds only where both overflowed;
the recommended build only on SubexponentialSAT and Hodge.

## Results

| configuration | where | master | master+71 | 64 MiB builds | master+71+guard.64M |
|---|---|---|---|---|---|
| 15 changed or deps-changed configurations | laptop | pass, 14–83 s | pass | – | – |
| LogspaceEquality | laptop | stack overflow | stack overflow | pass, 39–46 s, 2.7 GiB | – |
| DefocusingNLS | laptop and cloud | pass, 65–84 s | pass | – | – |
| LocalSmoothing | cloud | pass, 460 s, 10.5 GiB | pass, 463 s | – | – |
| SubexponentialSAT | cloud | stack overflow | stack overflow | stack overflow, ~24 GiB | **pass, 184 s, 27.0 GiB** |
| HodgeConjectureCMAbelianVarieties/main | cloud | **pass, 1,900 s, 20.0 GiB** | pass, 1,935 s | – | pass, 1,954 s |

"Stack overflow" is exit 134 with "thread '...' has overflowed its stack" in the full output
(confirmed in the logs for SubexponentialSAT). The SubexponentialSAT guard result was run twice;
the first run shared its export file with a concurrent run, the second ran alone, with the same
result. Hodge's export is 6.37 GB; its closure is 33,169 OAI modules (2.69 million lines),
built on the cloud in about 3.4 h of build time, during which Lean's kernel accepted every module.

nanoda here checks each solution's export with the configuration's permitted axioms; it does not
compare the theorem statement with the challenge's, which only Comparator does.

## Comparator

All 20 affected configurations have been run through Comparator, which compares each solution's
theorem statement and definitions with the challenge's and checks the axioms:

- **Comparator with Lean's kernel** (laptop, `local.jsonl`, logs in `logs/`): Rokhlin, Brenier,
  EuclideanFiveColor, KServer, LogspaceEquality, Naimark accepted.
- **Comparator with nanoda in place of Lean's replay** (cloud r7a.4xlarge, 2026-10-28,
  `tools/cloud_compare_update.sh`; `cloud/compare.jsonl`, full output in `cloud/logs/`): the other
  14, with Comparator built with `tools/patches/comparator-skip-builtin-kernel.patch` (sha256
  `9239d2775569`) and nanoda `master+71+guard.64M`. The only change to the published
  configurations is `"enable_nanoda": true` and `"skip_builtin_kernel": true`
  (`cloud/compare-config-edits.patch`). 13 accepted, in 110–618 s each.
- **HodgeConjectureCMAbelianVarieties/main is rejected**, at the statement comparison, before any
  kernel runs: `Challenge and solution theorem statement do not match:
  'HodgeCM.hodge_conjecture_for_cm_abelian_varieties'`. The same rejection with the configuration
  exactly as published (`cloud/hodge-published.json`, output `cloud/hodge-stock-comparator.log`;
  the same Comparator binary, whose patch is inactive without `skip_builtin_kernel`).

**Why Hodge fails.** `Solution.lean` states the theorem with OAI's own copies of the definitions
(`OAI.AlgebraicGeometry.Foundations.ProjectiveSpaceIs.IsProjective`,
`OAI.AlgebraicGeometry.ComplexMultiplication.Definitions.HasComplexMultiplication`,
`OAI.AlgebraicGeometry.ComplexPoint.Basic.ComplexSchemePoint.algebraicCycleClassSpan`), while
`Challenge.lean` uses those of its 259-module helper library (credited in `lean/docs/032.md` to
Paul-Lez/HodgeConjecture) and its own `CM.lean`. `tools/find_bridge.py` finds that the challenge's
closure (259 in-repo modules) and the solution's (33,170) share no module, that no module in the
solution's closure imports anything on the challenge's side, and that no file anywhere under `OAI/`
(162,417 scanned) does either, so no lemma relating the two sets of definitions can exist in the
published files. The solution itself builds (Lean's kernel accepted every module) and nanoda
accepts its export; what fails is the match with the challenge's statement. The same doubt was
raised on the Lean Zulip by Joseph Myers and Kevin Buzzard, without a Comparator run:
https://leanprover.zulipchat.com/#narrow/channel/583339-AI-authored-projects/topic/OpenAI.20releases.20solutions.20to.20hundreds.20of.20problems/with/635342154

## Machines and gaps

Laptop (`yl`, 16 threads); cloud: spot r6a.8xlarge (reclaimed four times, the driver resumed
from the boot hook) and then on-demand r7a.8xlarge, both with the data volume holding the full
fd4aeeb2ee build. Full Lake output of the cloud builds with per-module times:
`cloud/cloud-builds.log`. The Lake output of the laptop closure builds
(`tools/build_config_closures.py`) was not kept; only a count per configuration.
