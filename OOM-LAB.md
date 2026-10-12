# Memory-pressure lab: why a memory kill took the browser, the terminal and a build together

Background (verified from the journal, 2026-10-11): at 18:00:53 `systemd-oomd` killed one cgroup
(`xdg-desktop-portal.service`, 292 processes) because memory pressure in the user session
(`user@1000.service`) was 67% against a 50% limit for more than 20 s. The kernel OOM killer never
ran. Per `oomd.conf(5)` and `systemd-oomd(8)`: candidates are leaf cgroups (or those with
`memory.oom.group=1`), ranked from most to least reclaim activity, and everything in the chosen
cgroup is killed. So what dies together is whatever shares a leaf cgroup. The terminal tab's scope
held this Claude Code session, tmux, the pipeline and every Lean process (49 GiB) while Chrome ran
elsewhere; at 18:00 a different layout put the browser and the workload in one victim.

## Questions
1. Which cgroup does each precious thing (Chrome, Zoom, Claude Code, tmux, Emacs, the desktop) land
   in after a fresh login?
2. Is the victim really the leaf cgroup with the highest reclaim rate (pgscan), as documented?
3. Does `ManagedOOMPreference=avoid` on the desktop's scopes keep them alive while a memory hog is
   killed instead?
4. Does running the pipeline as its own systemd service make it the only casualty?
5. How long from pressure above the limit to the kill, and what do the settings in `oomd.conf`
   (`SwapUsedLimit=`, `DefaultMemoryPressureLimit=`, `DefaultMemoryPressureDurationSec=`) change?

## Tools (all in tools/)
- `cgroup_census.py`  who shares a cgroup; memory, swap, pressure, pgscan/s; the likely victim
  first. Read-only.
- `oom_watch.py`      1 Hz JSON-lines recorder (pressure, available memory, top cgroups, vanished
  cgroups, oomd journal lines).
- `memhog.py`         allocates and thrashes anonymous memory, to be run inside a named transient
  scope.
- `stop_run.sh` / `start_run.sh`   stop and restart the Comparator run.

## Setup after the reboot (do not start the pipeline yet)
1. Log in; open Chrome with the usual tabs, Zoom, Claude Desktop, the terminal. Save open work.
2. `systemd-run --user --unit=oom-watch --collect python3 -I tools/oom_watch.py` (its own cgroup,
   tiny).
3. `python3 tools/cgroup_census.py` and keep the output (Q1).
4. Optionally, as root, fix `/etc/systemd/oomd.conf.d/99-lower-swap-threshold.conf` (key
   `SwapUsedLimit=70%`).

## Experiments (each: run, wait for recovery, note what died, read `journalctl -u systemd-oomd --since -5min`)
- V1 hog alone:
  `systemd-run --user --scope --unit=memhog python3 tools/memhog.py --gib 70 --rate 600 --max-seconds 240`
  Expect: pressure above 50% for 20 s, then oomd kills the `memhog.scope`. Note whether Chrome or
  anything else dies too.
- V2 bad neighbours:
  `systemd-run --user --scope --unit=fake-terminal bash -c 'sleep 1d & sleep 1d & python3 tools/memhog.py --gib 70 --max-seconds 240'`
  Expect: the sleeps die with the hog (collateral inside one leaf cgroup).
- V3 protect the precious: find scopes with `python3 tools/cgroup_census.py`, then for Chrome,
  Claude Desktop, gnome-shell:
  `systemctl --user set-property --runtime <scope> ManagedOOMPreference=avoid`; repeat V1 and V2.
  Expect: the hog dies, the avoided cgroups survive. (Runtime-only, so it must be reapplied after
  each login.)
- V4 isolate the workload: start the pipeline with
  `systemd-run --user --unit=oai-pipeline python3 -I tools/pipeline.py ...` (a service, not a child
  of the terminal), check with the census that it has its own leaf cgroup, then run V1 while it
  builds. Expect: the pipeline service or the hog goes, never the terminal, tmux or Claude.
- V5 timing: compare time-to-kill across `DefaultMemoryPressureDurationSec` values if you change the
  config.

## Safety
The machine may freeze for tens of seconds. `--max-seconds` is a dead-man switch (the hog exits by
itself). To abort: `systemctl --user stop memhog.scope`. Do not run the Comparator pipeline during
the experiments.

## Record
Keep `results/oom-lab/watch.jsonl` and the journal excerpts; write the answers to the five questions
in REPORT.md.
