# Independent verification and resource benchmarking of OpenAI/math

You are Claude Code running on my Ubuntu Linux workstation. Act as an autonomous research engineer, systems programmer, and cloud-infrastructure orchestrator.

## Objectives

Investigate and reproduce the available Lean formalizations in:

https://github.com/openai/math

The repository contains hundreds of mathematical manuscripts and a very large Lean library.

Our primary questions are:

1. What is the minimum Linux `vm.max_map_count` that allows the **entire Lean library** to compile and check successfully?
2. How does the threshold depend on the Lean version, memory allocator, build parallelism, and workload?
3. How does the normal Lean build compare in wall-clock time, CPU usage, memory consumption, mapping counts, and total cost with a Lean build using `-DMMAP=OFF`?
4. Does the additional `GLIBC_TUNABLES=glibc.malloc.mmap_max=0:glibc.malloc.arena_max=1` setting help, hurt, or make no difference?
5. Can we independently check every available formalized result, including Comparator configurations, while clearly documenting what is and is not verified?

This is a reproducibility and resource-measurement project, not an attempt to generate new mathematical proofs.

## Local workstation and cloud architecture

My workstation:
- Ubuntu Linux, approximately 60 GiB RAM, 16 logical CPUs.
- Claude Code runs here as the primary orchestrator.
- Preserve my existing development environment and system configuration.
- Place all project files in a dedicated working directory.
- Do not modify global sysctl settings or install system packages without appropriate approval.

Cloud resources:
- DigitalOcean account, with `doctl`/API support, is the first choice.
- Existing AWS and Google Cloud accounts are alternatives.
- Hetzner is a potential additional provider.
- Fly.io Sprites are available but not a preferred heavy-compute platform.

Before committing to a provider, inspect available CLI credentials and authenticated contexts without displaying or copying secrets. Determine applicable quotas, promotions, credits, machine sizes, and current rates.

Investigate whether a suitable existing instance or unused cloud credit can be employed.

Use my workstation for orchestration, scripts, monitoring control, logs, results, and final reporting. Use ephemeral cloud machines for heavy compilation and verification.

Keep long-running remote work independent of the workstation's SSH connection. Use systemd, tmux, or another robust mechanism, with resumable jobs and logs.

Avoid having Claude repeatedly poll jobs in a way that unnecessarily consumes model tokens. Prefer scripts that perform deterministic operations and record durable, structured results.

## Budget and approval

Begin with an estimated $10 experimental budget and a proposed $50 overall ceiling.

Do not create chargeable cloud infrastructure until I approve the provider, machine type, maximum estimated cost, and cleanup policy.

Once approved, you may perform the planned experiments autonomously within the approved budget.

Set cost safeguards, record creation and destruction times, and automatically clean up unneeded compute resources.

Preserve results locally before terminating instances. Do not incur continuing storage, snapshot, or address charges without approval.

Escalate if the total estimated expense will exceed the approved ceiling.

## Phase 1: Repository reconnaissance

Inspect the actual repository before designing implementation details.

- Pin an exact Git commit.
- Read the Lean README and Comparator instructions.
- Inspect `lean-toolchain`, `lakefile.toml`, `lake-manifest.json`, and the Lean build targets.
- Identify the complete library build command and relevant import structure.
- Enumerate available formalizations and Comparator configurations.
- Determine whether cached Lean/mathlib build artifacts are available.
- Investigate Lean's current memory allocator, CMake `MMAP` option, and glibc malloc interaction using authoritative implementation and documentation sources.
- Examine public discussions or issues relevant to full builds and mmap failures.

Do not assume that the repository's source-file count is equivalent to the number of modules that a particular Lake target compiles.

Document any complications in defining "the entire library."

## Phase 2: Local development and instrumentation

Develop portable instrumentation locally before renting a large VM.

Implement a process monitor that records:

- Timestamp and process identifier
- Command line and parent process
- Virtual memory area (VMA) count
- Resident and peak memory usage
- CPU time and processor utilization
- Page faults
- I/O volume
- Exit code and termination reason

Record the peak **per-process** VMA count, not simply the sum across processes. Also measure aggregate memory pressure and concurrency.

A basic `/proc/PID/maps` sampler is acceptable initially. However, sampling can miss short-lived peaks, so implement a more reliable threshold-verification strategy.

Compare available approaches such as low-overhead tracing, Linux process accounting, eBPF, and repeatable boundary tests. Avoid instrumentation whose overhead would materially bias performance measurements.

Distinguish:
- VMA-limit exhaustion
- Physical memory exhaustion
- `RLIMIT_AS` or other resource limits
- Storage exhaustion
- Build failures unrelated to resources

Use explicit error classification rather than inferring that every failure results from `vm.max_map_count`.

## Phase 3: Initial cloud experiments

Recommend an economical first cloud machine, perhaps 8–16 vCPUs and 32–64 GiB RAM, after investigating the actual options.

Use standard Lean with its default mmap behavior.

Start with a sufficiently high mapping limit, subject to kernel constraints, and attempt a meaningful build. Monitor module-level resource consumption.

Increase VM size only if measurements justify doing so.

Preserve compiled dependencies between experiments whenever safe. Separate cold-build costs from warm-build costs.

If possible, identify a small reproducible target or module that exhibits the mapping failure. This would make subsequent experiments considerably cheaper.

## Phase 4: Establish `vm.max_map_count` thresholds

Find the lowest mapping limit that reliably permits the full build on the selected machine and software stack.

Use a measured upper bound, then binary search or another systematic method to locate the success/failure boundary.

Perform repeated trials, using controlled caches and build configurations.

Do not lower a mapping limit below the current number of mappings in any process under test without understanding Linux's behavior.

Compare results at several parallelism levels, for example 1, 4, 8, and the machine's practical maximum.

Determine whether the mapping threshold depends mainly on an unusually large Lean process, concurrency, or allocator behavior.

Report separately:
- Highest observed VMA count
- Lowest observed successful limit
- Highest observed failing limit
- Confidence/reproducibility
- Recommended operational value with headroom

If the full build is not achievable within the budget, report the strongest valid partial bounds and the resources necessary to finish.

## Phase 5: Benchmark allocation alternatives

Compare the following configurations:

A. Standard Lean allocator with raised `vm.max_map_count`.

B. Lean compiled with `-DMMAP=OFF`.

C. The same as B with the documented `GLIBC_TUNABLES` settings.

Optionally test the glibc tunables independently if meaningful.

Use identical source commits and dependencies. Follow the actual Lean build instructions for alternative compiler configurations and verify that the intended allocation settings are active.

Avoid mixing incompatible build artifacts between Lean toolchain configurations.

Measure:
- Cold and warm wall-clock build times
- CPU-seconds
- Peak RAM
- Peak VMA count
- Storage usage
- Failures and retries
- Cloud cost
- Changes in swapping, allocator contention, or fragmentation if observable

Run repeated representative trials and report variability. Do not claim that a small measured difference is meaningful without sufficient evidence.

Determine whether `MMAP=OFF` actually improves efficiency, or merely avoids a Linux kernel resource limit that can be raised cheaply.

## Phase 6: Formal verification

Use the repository's documented procedures to check the available Lean formalizations.

Attempt the complete library build.

Then enumerate and check available Comparator configurations using the appropriate tools, such as Comparator, landrun, and lean4export.

Do not assume every manuscript has a formalization or every Comparator configuration checks a headline theorem.

Produce a machine-readable inventory identifying:
- Manuscript or mathematical family
- Formalized declaration or target
- Lean build result
- Comparator result, when applicable
- Axioms or assumptions involved
- Whether it verifies the principal result or a supporting result
- Any unverified aspects or dependencies

Do not equate successful compilation with validation of the original informal mathematical argument. Distinguish the exact proposition checked from the corresponding manuscript claim.

## Phase 7: Reproducibility and release

Produce a small standalone project containing:

- `README.md`
- `run.sh` or equivalent entry point
- Provisioning and cleanup scripts
- Measurement scripts
- Experiment configuration in YAML or TOML
- Machine-readable results in CSV/JSON
- Complete logs or compressed log archives
- A concise technical report
- A manifest recording exact software commits, operating-system/kernel versions, instance details, and commands

The project must be useful to other Lean developers, not merely to users of OpenAI/math.

Make experiments rerunnable without cloud infrastructure if an adequate local machine is available.

The final report must answer:

**What mapping limit is required, how confident are we, and what is the best allocation configuration in terms of both runtime and cost?**

Include a proposed concise documentation patch for the OpenAI/math README, suitable for upstream contribution.

## Operating principles

- Prefer simple, inspectable shell and Python tools.
- Use version control from the beginning.
- Make all experiments repeatable and resumable.
- Never pipe an unreviewed remote installation script directly into a shell.
- Preserve logs and diagnostic artifacts.
- Use least-privilege cloud credentials and SSH keys.
- Never leak tokens, passwords, or API keys into logs or Git.
- Avoid unnecessary local system changes.
- Make actual measurements rather than inventing runtime or cost estimates.
- Distinguish observations, hypotheses, and conclusions.
- Use ISO 8601 timestamps.

Start by inspecting the repository, the local environment, and available cloud provider authentication. Present a short experimental plan and cost comparison before creating chargeable resources.

Once I approve a budget and provider, implement and conduct the experiments with minimal supervision. Stop only for a genuine blocker, significant change of scope, or additional spending authorization.
