# nanoda on the October 2026 OpenAI Yang-Mills Lean submission

The Yang-Mills group (github.com/yang-mills-group) published OpenAI's Lean submission of 2026-10-28
(`yang-mills-group/OpenAI-YM-20261028`) and its initial assessment (`yang-mills-group/YM`,
`docs/assessment-1.pdf`, 2026-11-10). Their checks used Comparator with Lean's kernel only ("An
additional external kernel implementation was not used"). This is a second-kernel check of the same
target, `YangMills.jointExistence`, with nanoda_lib.

## Inputs

- `yang-mills-group/YM` at `55ba9fc36293b3f4d52c6b1f813169a0be76ee98`, package
  `submissions/openai-20261028/`: its integrity check (`scripts/verify.py integrity`, every file
  against its hash) passed, and its build stage (`scripts/verify.py build`: Mathlib cache, `lake
  build WilsonReference WilsonConstruction`, Lean 4.32.0, Mathlib `81a5d257c8e4`) passed in 1 h 31
  min on 32 vCPUs.
- lean4export at their pin `4e7915201d3f9f04470d9eae002fa695f7cdc589` (Lean 4.32.0, export format
  3.1.0). The export of `Solution` with Comparator's declaration list (`verification/submission.json`:
  the theorem, `propext`, `Quot.sound`, `Classical.choice` and the kernel primitives) is 3.22 GB
  (3,222,392,184 bytes), made in 4.9 min.
- nanoda_lib master `0da9f98fea` (2026-11-07), built with `tools/build_nanoda_variant.sh`
  (descriptions in `nanoda-builds/`):

| label | sha256 (first 12) | source | checker stack |
|---|---|---|---|
| `master` | `3349b4957187` | master | 32 MiB (default) |
| `master+71.64M` | `054b25381958` | master + PR 71 (`infer-let-local` at `19226226ad`) | 64 MiB |
| `master+71+guard.64M` | `ce4bc7b88e00` | master + PR 71 + `tools/patches/nanoda-succ-fvars-guard.patch` | 64 MiB |
| `master+guard.64M` | `41d1b1737d24` | master + the guard patch | 64 MiB |

The stack is nanoda's `stack_size_bytes` setting, passed by `tools/nanoda_ab.py --stack-bytes`.

## Results

16 threads, on an isolated spot c7a.8xlarge (32 vCPU, 61 GiB) with no IAM role, the instance
metadata service off and none of our data (`tools/cloud_spot_scratch_launch.sh`,
`tools/cloud_yang_mills_nanoda.sh`):

| build | result |
|---|---|
| `master` | killed at its 50G memory cap after 25 min (41 CPU-minutes), at 52.3 GB resident: systemd `oom-kill` (instance journal; not in `nanoda.jsonl`) |
| `master+71.64M` | exit 0 in 167.4 s, 18.3 CPU-minutes, 7.39 GiB peak |
| `master+71+guard.64M` | exit 0 in 165.5 s, 18.3 CPU-minutes, 7.34 GiB peak |
| `master+guard.64M` | not finished: two spot reclaims stopped it |

The accepted runs have nanoda's exit status and `/usr/bin/time`'s summary in their full logs
(`nanoda-logs/`). PR 71 alone makes the difference: without it nanoda's memory grows past 50 GB
without an answer, with it the check finishes in under three minutes at 7.4 GiB, much as for
`OAI.SquareDifference.source_ordered_contraction` in openai/math (nanoda_lib issue 62).

nanoda checks the export of the solution against the permitted axioms; it does not compare the
statement with the challenge, which the group's Comparator runs do. Whether the formal statement
captures the physics, and what the result establishes, is the subject of the group's assessment,
which describes itself as initial.
