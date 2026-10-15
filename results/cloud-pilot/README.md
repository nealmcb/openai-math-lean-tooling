# Cloud pilot: two configurations on one AWS m7a.2xlarge

Purpose: measure how fast the work runs on a cloud machine, to refine the schedule model
(`tools/cloud_schedule_model.py`) and the cost estimate in `CLOUD-PLAN.md`.

Machine: m7a.2xlarge (8 vCPU AMD EPYC 9R14, 32 GiB), Ubuntu 24.04, kernel 7.0, 120 GB gp3, us-east-1,
on-demand. Set up from nothing by `tools/cloud_bootstrap.sh` (log: `bootstrap.log`): 3 min 20 s in
total, of which `lake update` 2 min, the Mathlib cache download 16 s (8,908 files), and landrun,
lean4export and comparator 15 s. The run used `tools/run_comparator_batch.py` with the default
`vm.max_map_count` of 65530; per-config records are in `cmp-pilot/all.jsonl`, logs in `cmp-pilot/logs`.

| | MatchingFPRAS | FourierLLogL |
|---|---|---|
| Modules built (not in the Mathlib cache) | 416 | 157 |
| Sum of module compile times, cloud | 2,403 s | 876 s |
| Same modules, first build on the laptop (under load) | 8,978 s | 4,213 s |
| Compile speed-up | 3.7 | 4.8 |
| Build wall time on 8 vCPU | 604 s | 467 s |
| Check wall time, cloud | 151 s | 151 s |
| Check active time, laptop | 204 s | 158 s |
| Check speed-up | 1.35 | 1.05 |
| Check peak memory | 7.3 GiB | 7.2 GiB |
| Peak mappings, build / check | 54,220 / 54,197 | 53,981 / 53,940 |

Both configurations were accepted. The compile speed-up is an upper bound because the laptop times
come from a loaded, thermally limited machine; the check speed-up is small because the kernel check is
single-threaded and the laptop's cores boost high for one thread. Not tested: more than 8 vCPU, the
disk volume of a full run, and the second kernel (nanoda).
