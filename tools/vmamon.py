#!/usr/bin/env python3
"""vmamon: run a command and record per-process VMA counts and resource usage.

Purpose: measure the PEAK PER-PROCESS number of virtual memory areas (lines in
/proc/PID/maps) reached by any process in the command's process tree, since
vm.max_map_count limits each process separately (not the sum). Also records peak
RSS, aggregate RSS/process concurrency, CPU time, page faults, and I/O, and
classifies the exit reason (VMA limit vs OOM vs other) explicitly.

Sampling can miss short-lived peaks; results are LOWER bounds on the true peak.
Threshold claims must be verified by boundary tests (run at limit N and N-1),
not by sampled peaks alone. See ../REPORT.md.

Usage: vmamon.py --out DIR [--interval 0.05] -- cmd args...
Writes DIR/summary.json (including export_timeline and export_done_s for lean4export processes) and DIR/samples.jsonl (one line per sample with changed
per-process maxima only, to keep logs small) and DIR/stdout.log (merged output).
"""
import argparse, json, os, re, subprocess, sys, time, signal, datetime

PAGE = os.sysconf("SC_PAGE_SIZE")


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")


def read_proc(pid):
    """Return dict of stats for pid, or None if it vanished."""
    try:
        with open(f"/proc/{pid}/maps", "rb") as f:
            vmas = f.read().count(b"\n")
        with open(f"/proc/{pid}/stat", "rb") as f:
            raw = f.read().decode(errors="replace")
        # comm may contain spaces/parens: split after last ')'
        rest = raw[raw.rindex(")") + 2:].split()
        ppid = int(rest[1]); minflt = int(rest[7]); majflt = int(rest[9])
        utime = int(rest[11]); stime = int(rest[12])
        rss = int(rest[21]) * PAGE
        comm = raw[raw.index("(") + 1:raw.rindex(")")]
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode(errors="replace").strip()
        except OSError:
            cmd = ""
        io = {}
        try:
            with open(f"/proc/{pid}/io") as f:
                for line in f:
                    k, v = line.split(":"); io[k] = int(v)
        except OSError:
            pass
        return dict(pid=pid, ppid=ppid, vmas=vmas, rss=rss, minflt=minflt, majflt=majflt,
                    cpu_ticks=utime + stime, comm=comm, cmd=cmd[:300],
                    rchar=io.get("rchar", 0), wchar=io.get("wchar", 0))
    except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError, IndexError):
        return None


def descendants(root):
    """All pids in the tree under root, via a single /proc scan."""
    children = {}
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat", "rb") as f:
                raw = f.read().decode(errors="replace")
            ppid = int(raw[raw.rindex(")") + 2:].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        children.setdefault(ppid, []).append(int(name))
    out, stack = [], [root]
    while stack:
        p = stack.pop()
        out.append(p)
        stack.extend(children.get(p, []))
    return out


def meminfo_kb(key):
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith(key + ":"):
                return int(line.split()[1])


def classify(rc, output_tail, oom_kills_delta, vmas_peak, limit):
    """Explicit classification; never infer a VMA failure from exit code alone."""
    if rc == 0:
        return "success"
    t = output_tail
    if oom_kills_delta > 0 or rc in (-9, 137) and re.search(r"[Kk]illed", t):
        return "oom_killed_or_sigkill"
    if re.search(r"No space left on device", t):
        return "storage_exhausted"
    if re.search(r"Cannot allocate memory|std::bad_alloc|out of memory|mmap failed|ENOMEM|failed to read file .*\.olean", t):
        # ENOMEM from mmap/brk is what vm.max_map_count exhaustion produces,
        # but RLIMIT_AS or physical exhaustion look the same: disambiguate with VMA peak.
        if limit and vmas_peak >= 0.97 * limit:
            return "vma_limit_likely (ENOMEM with sampled VMA peak near limit)"
        return "enomem_unattributed (check RLIMIT_AS / RAM / VMA)"
    if rc < 0:
        return f"signal_{-rc}"
    return "build_failure_unclassified"


def vmstat_oom():
    try:
        with open("/proc/vmstat") as f:
            for line in f:
                if line.startswith("oom_kill "):
                    return int(line.split()[1])
    except OSError:
        pass
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--interval", type=float, default=0.05)
    ap.add_argument("--label", default="")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    os.makedirs(a.out, exist_ok=True)
    limit = int(open("/proc/sys/vm/max_map_count").read())
    oom0 = vmstat_oom()
    t0 = time.time()
    logf = open(os.path.join(a.out, "stdout.log"), "wb")
    p = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, start_new_session=True)
    seen = {}      # pid -> best stats (max vmas etc.)
    samples = open(os.path.join(a.out, "samples.jsonl"), "w")
    peak_total_rss = peak_procs = peak_total_vmas = 0
    min_avail_kb = meminfo_kb("MemAvailable")
    nsamples = 0
    while p.poll() is None:
        ts = time.time()
        stats = [s for s in (read_proc(pid) for pid in descendants(p.pid)) if s]
        nsamples += 1
        peak_procs = max(peak_procs, len(stats))
        peak_total_rss = max(peak_total_rss, sum(s["rss"] for s in stats))
        peak_total_vmas = max(peak_total_vmas, sum(s["vmas"] for s in stats))
        min_avail_kb = min(min_avail_kb, meminfo_kb("MemAvailable"))
        for s in stats:
            old = seen.get(s["pid"])
            if old is None:
                seen[s["pid"]] = dict(s, first_ts=ts, max_vmas=s["vmas"], max_rss=s["rss"], max_rchar=s["rchar"], max_wchar=s["wchar"])
            else:
                nv = max(old["max_vmas"], s["vmas"]); nr = max(old["max_rss"], s["rss"])
                grew = nv > old["max_vmas"]
                mrc = max(old.get("max_rchar", 0), s["rchar"]); mwc = max(old.get("max_wchar", 0), s["wchar"])   # counters only grow; an exiting process reads as 0
                old.update(s, first_ts=old["first_ts"], max_vmas=nv, max_rss=nr, last_ts=ts, max_rchar=mrc, max_wchar=mwc)
                if grew:
                    samples.write(json.dumps(dict(t=round(ts - t0, 3), pid=s["pid"], vmas=nv)) + "\n")
            seen[s["pid"]]["last_ts"] = ts
        time.sleep(a.interval)
    rc = p.returncode
    wall = time.time() - t0
    logf.close()
    samples.close()
    with open(os.path.join(a.out, "stdout.log"), "rb") as f:
        f.seek(0, 2); n = f.tell(); f.seek(max(0, n - 20000))
        tail = f.read().decode(errors="replace")
    top = sorted(seen.values(), key=lambda s: -s["max_vmas"])[:10]
    ru = os.wait4 if False else None
    vmas_peak = top[0]["max_vmas"] if top else 0
    clk = os.sysconf("SC_CLK_TCK")
    summary = dict(
        label=a.label, cmd=cmd, started=datetime.datetime.fromtimestamp(t0, datetime.timezone.utc).isoformat(timespec="seconds"),
        wall_s=round(wall, 3), exit_code=rc, vm_max_map_count=limit, samples=nsamples, interval_s=a.interval,
        peak_per_process_vmas_sampled=vmas_peak, peak_concurrent_processes=peak_procs,
        peak_sum_vmas_sampled=peak_total_vmas, peak_sum_rss_bytes=peak_total_rss,
        min_mem_available_kb=min_avail_kb, oom_kills_during=vmstat_oom() - oom0,
        classification=classify(rc, tail, vmstat_oom() - oom0, vmas_peak, limit),
        top_processes=[dict(pid=s["pid"], comm=s["comm"], cmd=s["cmd"], max_vmas=s["max_vmas"],
                            max_rss=s["max_rss"], cpu_s=round(s["cpu_ticks"] / clk, 2),
                            minflt=s["minflt"], majflt=s["majflt"], rchar=s.get("max_rchar", s["rchar"]), wchar=s.get("max_wchar", s["wchar"]))
                       for s in top],
        note="sampled peaks are lower bounds; verify thresholds with boundary runs",
    )
    # export size: bytes written to stdout by each lean4export process (Comparator streams the export from it); sampled, so a lower bound
    exp = sorted((v.get("max_wchar", 0) for v in seen.values() if v["comm"] == "lean4export"), reverse=True)
    summary["export_bytes_total"] = sum(exp); summary["export_bytes_largest"] = exp[0] if exp else 0
    summary["export_processes"] = len(exp)
    # when each lean4export process ran, in seconds after the start of the monitored command: its sampled start and end bound the export
    # phase (the kernel check of the solution follows the last export), and its bytes are the export size known at that point
    tl = sorted((v for v in seen.values() if v["comm"] == "lean4export"), key=lambda v: v["first_ts"])
    summary["export_timeline"] = [dict(pid=v["pid"], start_s=round(v["first_ts"] - t0, 1), end_s=round(v.get("last_ts", v["first_ts"]) - t0, 1),
                                       bytes=v.get("max_wchar", 0), max_rss_bytes=v["max_rss"]) for v in tl]
    summary["export_done_s"] = max((e["end_s"] for e in summary["export_timeline"]), default=None)
    # the kernel phases of a Comparator check: the nanoda checker (comm nanoda_bin) and Lean's own kernel (comm lean) run one after the other
    # on the solution; sampled start and end seconds after the start of the monitored command, with their CPU time and peak memory
    summary["kernel_timeline"] = [dict(comm=v["comm"], pid=v["pid"], start_s=round(v["first_ts"] - t0, 1), end_s=round(v.get("last_ts", v["first_ts"]) - t0, 1),
                                       cpu_s=round(v["cpu_ticks"] / clk, 1), max_rss_bytes=v["max_rss"])
                                  for v in sorted(seen.values(), key=lambda v: v["first_ts"]) if v["comm"] in ("nanoda_bin", "lean") and v["cpu_ticks"] / clk >= 1]
    # CPU time of all waited children (reliable, not sampled)
    ch = os.times()
    summary["children_cpu_user_s"] = round(ch.children_user, 2)
    summary["children_cpu_sys_s"] = round(ch.children_system, 2)
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps({k: summary[k] for k in ("wall_s", "exit_code", "peak_per_process_vmas_sampled",
                                              "peak_concurrent_processes", "classification")}))
    sys.exit(0 if rc == 0 else 1)


if __name__ == "__main__":
    main()
