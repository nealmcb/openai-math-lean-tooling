# Nanoda thread scaling on a cloud machine

Purpose: how nanoda's checking time changes with the number of threads. Comparator always gives it 4 (`num_threads` in the config it writes); here nanoda_bin was run
directly on exports (no Lean, no Comparator) on a quiet c7a.16xlarge (64 vCPU, AMD EPYC 9R14, `lscpu.txt`) with the timing build of
`tools/patches/nanoda-stack-and-decl-times.patch` (1 GiB checker stack, per-declaration times). Tool: `tools/nanoda_scaling.py`; model: `tools/nanoda_thread_model.py`.

| Configuration (export) | Threads | Wall s | CPU s | Cores used | Speed-up over 4 | Peak memory GiB |
|---|---|---|---|---|---|---|
| SnakyTwentyOne (77 MB) | 4 | 193.7 | 533 | 2.75 | 1.00 | 5.6 |
| | 8 | 137.6 | 534 | 3.88 | 1.41 | 5.7 |
| | 16 | 112.5 | 547 | 4.87 | 1.72 | 6.0 |
| | 32 | 100.2 | 582 | 5.81 | 1.93 | 6.6 |
| | 64 | 95.5 | 696 | 7.29 | 2.03 | 7.6 |
| CycleCliqueRamsey (186 MB) | 4 | 681.5 | 2,717 | 3.99 | 1.00 | 1.0 |
| | 8 | 345.8 | 2,745 | 7.94 | 1.97 | 1.3 |
| | 16 | 183.8 | 2,893 | 15.74 | 3.71 | 1.9 |
| | 32 | 101.6 | 3,152 | 31.01 | 6.70 | 3.4 |
| | 64 | 64.9 | 3,898 | 60.07 | 10.50 | 6.4 |
| MatrixFields (612 MB) | 4 | 431.0 | 1,695 | 3.93 | 1.00 | 2.1 |
| | 8 | 223.3 | 1,718 | 7.69 | 1.93 | 2.2 |
| | 16 | 122.4 | 1,812 | 14.80 | 3.52 | 3.1 |
| | 32 | 68.6 | 1,903 | 27.72 | 6.28 | 5.1 |
| | 64 | 43.7 | 2,177 | 49.83 | 9.86 | 9.5 |
| PlanarPacking (3.85 GB), 64 threads only | 64 | 672.0 | 39,519 | 58.81 | n/a | 40.9 |

Findings:
- Parallelism is across declarations, so the limit is the longest single declaration plus the serial reading of the export. SnakyTwentyOne has one declaration of 86 s
  (`OAI.SnakyPrototype.Certificate21.child_envelope_sub_727._proof_1_1`, 18 export lines) out of 533 s of work, so 64 threads finish at 95 s, about that declaration.
- The other three scale almost linearly. PlanarPacking has 847,817 declarations, 39,559 s of work, a longest declaration of 15.8 s and 54 s of serial setup;
  the model predicts 672 s at 64 threads (measured 672.0 s), 363 s at 128. At 4 threads it would take about 9,900 s.
- CPU time grows with threads (CycleCliqueRamsey +43% from 4 to 64) and so does peak memory (0.97 to 6.4 GiB; PlanarPacking 40.9 GiB at 64).
- The per-declaration timing files of the first instance's CycleCliqueRamsey and MatrixFields runs were not retained; those kept are `planar/PlanarPacking.64.times.gz`
  (streaming format) and `SnakyTwentyOne.64.times`. Model output for PlanarPacking: `planar/PlanarPacking.model.txt`.
