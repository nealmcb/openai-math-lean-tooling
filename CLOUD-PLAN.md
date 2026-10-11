# Cloud plan: finishing and extending the openai/math Lean measurements

Status: proposal. Nothing has been created or spent. Prices are third-party figures from 2026-10-11
and must be confirmed with the provider before ordering. Speed-ups are estimates from measurements
on one laptop, stated below with their uncertainty.

## Why consider the cloud

The laptop (see REPORT.md section 1a) is running the Comparator checks on all 416 configurations and
will probably finish them itself, but three things argue for a second machine.

1. **Disk on the laptop.** Free space is 36 GB. The remaining work adds about 51,600 modules; at the
   measured 0.8 MB of `.olean` output plus 0.25 MB of archived C per module, and about 13 GB of
   uncompressed C for the batch in progress, the run needs roughly 50 to 65 GB more at its peak.
   Without freeing space or moving the build directory to another disk, the pipeline will start
   waiting for space (it stops below about 25 GB plus the next batch's estimate) before the work is
   done.
2. **Clean, repeatable timings.** The laptop is thermally limited: a sample under load showed the
   performance-core threads at 55% and the efficiency cores at 60% of their peak clocks, with about
   160 package-throttle events a second at 99 degrees C. Timings from it are indicative, not
   benchmarks, and the comparisons below need repeated trials without other work running.
3. **Independent reproduction** on a stock Ubuntu image, from a clean checkout, with the default
   `vm.max_map_count` of 65530.

What the laptop could do, and what limits it:

| Experiment | On the laptop |
|---|---|
| Root `OAI.lean` mapping measurement | Possible once the Comparator run completes. 84,543 of the root module's 91,762 imported modules will then be built; the other 7,219 need about 6 GB of `.olean` output (and about 42 GB of transient C, archivable). The measurement itself is `lake env lean OAI.lean` at a raised mapping limit and needs no C files. Memory is not the constraint (see below): the private heap is predicted at about 4 GiB, and the rest is evictable mapped file pages. Disk is: all the root's `.olean` files must be present, about 70 to 90 GB in total. |
| `MMAP=OFF` comparison | Possible on a subset. It needs a Lean built from source (cmake) as a second toolchain, a separate build tree (artifacts must not be mixed between toolchains), and repeated builds of a fixed set of modules. Capacity is tight at 36 GB free, and timings on a throttled laptop would be noisy. |
| `GLIBC_TUNABLES` comparison | Possible on the same subset; it is an environment variable. The cost is time and trial-to-trial noise, not disk. |

So the case for a second machine is disk headroom, quiet timings and repeatability, not that the
laptop cannot hold these experiments.

## Sizing

- **Cores.** The remaining build has an average of about 81 runnable modules (work divided by the
  longest dependency chain) and the longest chain is about 6 hours on the laptop's loaded times.
  Beyond roughly 100 cores there is little gain: the chain, plus the longest check, sets the floor.
  For comparison, the whole laptop is roughly equivalent to 6 cores of a 3.7 GHz server CPU for this
  workload (my estimate).
- **Memory.** About 1 to 2 GiB of real memory per concurrent Lean process on average, with some
  modules up to 10 GiB, so 192 concurrent processes need roughly 220 to 330 GiB. Checks use about
  6.5 GiB typically and up to 26 GiB. Choose 384 GiB for 192 vCPUs, or 192 GiB for 96.
- **Disk.** Do not bother compressing generated C here: about 630 GB of C plus 80 to 105 GB of
  `.olean` output plus 25 GB of packages, so provision 1.5 to 2 TB of SSD or NVMe. Peak writes
  average well under 100 MB/s.
- **Kernel.** Landlock is needed by the sandbox (Linux 5.13 or later; Ubuntu 22.04 or 24.04 images
  have it).

## Candidate machines

| Option | Price (third-party) | Estimated wall time, cost |
|---|---|---|
| AWS `c7a.48xlarge` (192 vCPU AMD, 384 GiB), on-demand ([Holori](https://calculator.holori.com/aws/ec2/c7a.48xlarge/us-east-1)) | about $9.85 per hour | 6 to 9 h, about $60 to $90 plus a few dollars of disk |
| Same, spot | about $3 per hour (July 2026 snapshot) | about $20 to $30; an interruption could lose hours of a long check |
| Half size (96 vCPU, 192 GiB) | about half the hourly price (not verified) | 9 to 14 h, about the same total |
| Hetzner AX162-R (48-core EPYC 9454P, 256 GB, 2 x 1.92 TB NVMe) ([WhTop](https://www.whtop.com/plans/hetzner.com/144082)) | EUR 199 per month, setup fee reported up to EUR 542 | 10 to 14 h; sensible only if the machine will be kept |

On-demand AWS exceeds the original $50 ceiling and needs explicit approval. DigitalOcean's size list
for the author's account stopped at 4 vCPUs, so it is not a candidate unless a limit increase is
granted.

## Run plan (about 9 hours on the large machine)

1. **Provision** the chosen instance with a 2 TB volume, Ubuntu 24.04 (or 22.04), and an automatic
   shutdown timer as a cost guard. Enable user lingering (`loginctl enable-linger`) so
   `systemd-run --user` works over ssh.
2. **Install** the same versions as MANIFEST.txt: elan with Lean 4.34.1, Go 1.24 or later, Rust (for
   nanoda), tmux. Build comparator, lean4export, landrun and nanoda at the manifest commits; set the
   first two projects' `lean-toolchain` to 4.34.1 so lean4export can read the project's `.olean`
   files.
3. **Fetch** openai/math at the pinned commit; run `lake update` (applies the compatibility patches)
   and `lake exe cache get`.
4. **Build everything once**: one `lake build` over every solution and challenge module under
   `tools/vmamon.py` (all cores), then Comparator on all 416 configurations with about 24 workers.
   The existing `tools/pipeline.py --cap-modules 200000 --max-configs 500 --workers 24` does this as
   a single batch; its archiving step is unnecessary with this much disk.
5. **Measure at the default limit** (65530) throughout, as on the laptop.
6. **Then, on the same machine and while it is still running:**
   - root `OAI.lean`: `lake env lean OAI.lean` under `tools/with_maxmap.sh` at 262144, then at
     1,048,576, recording peak mappings and memory (the 7,219 root-only modules must be built
     first);
   - build Lean from source with `-DMMAP=OFF` as a second toolchain, build a fixed subset (for
     example the `Progressions.Main` closure of 4,774 modules) with each of: standard Lean,
     `MMAP=OFF`, and `MMAP=OFF` with
     `GLIBC_TUNABLES=glibc.malloc.mmap_max=0:glibc.malloc.arena_max=1`, at least three trials each,
     recording wall time, CPU time, peak memory and mappings.
7. **Preserve results** by copying `results/`, the logs and the module times to the laptop before
   terminating; then terminate the instance and delete the volume. No snapshots, no retained
   addresses.

## Costs and approvals

- Approval needed before creating anything: provider, instance type, maximum estimated cost, cleanup
  policy.
- Estimated total on-demand: about $70 to $100 including disk and the extra experiments; spot about
  $25 to $40.
- Stop and ask if the running estimate approaches the approved ceiling.

## Risks and unknowns

- Per-core speed-ups come from clock and core-count arithmetic and have not been measured; a short
  pilot (an hour on a small instance, timing a fixed set of modules against the laptop) would turn
  the 6-to-9-hour estimate into a measured one at a cost of a few dollars.
- The long checks (`MUBSix` took 4.7 hours on the laptop) are the main tail risk: on spot, an
  interruption would lose that check's progress.
- The root import's memory is predicted from measurements at five sizes (REPORT.md section 3a), not
  measured at full size; the private heap grew by 0.042 MiB per imported OAI module, so the
  prediction would have to be badly wrong to matter on either machine.
- Lean's `MMAP=OFF` build and the interaction of the Mathlib cache with a self-built Lean have not
  been tried.
