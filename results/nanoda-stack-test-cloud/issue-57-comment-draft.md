# Posted comment on https://github.com/ammkrn/nanoda_lib/issues/57 (2026-10-16)

Interesting. But Claude says:

The one-line removal of the has_fvars check fixes the repro here too, but it brings back the #55 failure on one of the OpenAI configurations: ContinuumCoulombHardness passes on f67473b (130 s) and aborts with a stack overflow after 29 s with the check removed, with whnf and try_reduce_nat alternating about 58,000 times each in gdb, as in my first report. Five other configurations I re-ran behave as on master. I can share the 1.1 GB export if useful.
