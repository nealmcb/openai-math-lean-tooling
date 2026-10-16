# DRAFT (not posted) comment for https://github.com/ammkrn/nanoda_lib/issues/55

Excellent! Sorry I didn't look at your recent commits rather than just looking at the issues!

I rebuilt from the latest master (f67473b) and re-ran all 15 failing configurations on the same exports. 14 now pass, each in under 10 minutes and under 25 GiB (most in under a minute and under 1 GiB).

One still fails, SquareDifference, with a different recursion: a checker thread overflows its 16 MiB stack after about 22 s, and a gdb backtrace has 97,519 frames, 85,249 of them TypeChecker::def_eq and 12,178 TypeChecker::lazy_delta_step (no whnf / try_reduce_nat). The single declaration OAI.SquareDifference.tupleSubLaw_full reproduces it: a 75 MB export (1.7 MB zipped together with its config and the backtrace in the attached tupleSubLaw_full-repro.zip) overflows in 5.8 s with the default 4 threads, while Lean's kernel accepts it (1.8 s to parse, 5.8 s to replay). Two other declarations of that configuration, tupleLaw_decomposition and tupleGoodLaw_probability, overflow on their own too. A bigger checker stack (I made STACK_SIZE an environment variable locally) does not help the full configuration: 64 MiB overflows after 43 s, and 256 MiB and 1 GiB were killed by a 40 GiB memory limit after 2 min 20 s.

unzip tupleSubLaw_full-repro.zip
target/release/nanoda_bin nanoda-config-tupleSubLaw_full.json
The per-configuration timings are in results/nanoda-retest.jsonl and results/nanoda-retest-cloud.jsonl of https://github.com/nealmcb/openai-math-lean-tooling .

Happy to try other branches or commits.
