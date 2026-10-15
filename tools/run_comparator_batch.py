#!/usr/bin/env python3
"""run_comparator_batch: build and Comparator-check a list of configs, resumably, one JSON line each.

Purpose: measure per-config cost (solution build time vs Comparator time vs peak VMAs) and outcome for
OpenAI/math's ComparatorChallenges/*.json, to extrapolate to all 416 configs. Each Comparator run uses the
README-recommended systemd-run sandbox guard (RestrictAddressFamilies=~AF_UNIX) and landrun (inside comparator).
Results append to OUT.jsonl; configs already present there are skipped (resumable). Stops cleanly if
STOP file exists. Outcome is parsed from Comparator's own output, never inferred from the exit code alone.

Usage: run_comparator_batch.py LEAN_ROOT OUT.jsonl CONFIG_NAME [CONFIG_NAME...]
  (CONFIG_NAME = ComparatorChallenges/<name>.json basename without .json)
Env: needs landrun and lean4export on PATH (see ../MANIFEST.txt), COMPARATOR_BIN optional. Each check runs in a systemd unit named
cmp-<config> (so it can be stopped on its own, and a second check of the same config is skipped); CHECK_MEMMAX (e.g. 30G) caps its memory; CHECK_CPUS (e.g. 24-31) pins it to those CPUs with taskset.
A check stopped by tools/check_scheduler.py is recorded as outcome "preempted" and is to be re-run.
"""
import sys, os, json, time, subprocess, re, tempfile, datetime

root, out, names = sys.argv[1], sys.argv[2], sys.argv[3:]
here = os.path.dirname(os.path.abspath(__file__))
comparator = os.environ.get("COMPARATOR_BIN", os.path.join(here, "../ext/comparator/.lake/build/bin/comparator"))
done = set()
if os.path.exists(out):
    done = {json.loads(l)["config"] for l in open(out) if l.strip() and json.loads(l).get("outcome") == "accepted"}
stopfile = os.path.join(os.path.dirname(os.path.abspath(out)), "STOP")


def run(cmd, log):
    t = time.time()
    with open(log, "wb") as f:
        p = subprocess.run(cmd, cwd=root, stdout=f, stderr=subprocess.STDOUT)
    return p.returncode, time.time() - t


def tail(path, n=3000):
    with open(path, "rb") as f:
        f.seek(0, 2); s = f.tell(); f.seek(max(0, s - n))
        return f.read().decode(errors="replace")


def load_json_rows(path, key):
    d = {}
    if os.path.exists(path):
        for l in open(path):
            r = json.loads(l); d[r[key]] = r
    return d


CLOSURE = load_json_rows(os.path.join(here, "../results/solution-closure-sizes.jsonl"), "module")
PRED = load_json_rows(os.path.join(here, "../results/predicted-vmas.jsonl"), "module")


def build_stats(text):
    times = [(float(t), m) for m, t in re.findall(r"Built (\S+) \(([\d.]+)s\)", text)]
    mins = [(float(a) * 60 + float(b), m) for m, a, b in re.findall(r"Built (\S+) \((\d+)m ([\d.]+)s\)", text)]
    allt = sorted(times + mins, reverse=True)
    return dict(modules_built_this_run=len(allt), slowest_modules=[dict(module=m, s=t) for t, m in allt[:3]],
                sum_module_s=round(sum(t for t, _ in allt), 1))


def snap():
    import shutil
    return dict(load1=round(os.getloadavg()[0], 1), free_gib=round(shutil.disk_usage("/home").free / 2**30, 1))


for name in names:
    if name in done:
        continue
    if os.path.exists(stopfile):
        print("STOP file present; exiting"); break
    if subprocess.run(["systemctl", "--user", "is-active", "--quiet", f"cmp-{name}"]).returncode == 0:
        print(name, "is already being checked (unit cmp-%s); skipping" % name, flush=True); continue
    cfg = json.load(open(os.path.join(root, f"ComparatorChallenges/{name}.json")))
    logdir = os.path.join(os.path.dirname(os.path.abspath(out)), "logs"); os.makedirs(logdir, exist_ok=True)
    rec = dict(config=name, solution=cfg["solution_module"], challenge=cfg["challenge_module"],
               nanoda=bool(cfg.get("enable_nanoda")), started=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"))
    sol = cfg["solution_module"]
    srcf = os.path.join(root, *sol.split(".")) + ".lean"
    rec.update(closure_in_repo=CLOSURE.get(sol, {}).get("in_repo_closure"), predicted_vmas=PRED.get(sol, {}).get("predicted_vmas"),
               predicted_ext_module_system=PRED.get(sol, {}).get("ext_module_system"), theorem_count=len(cfg.get("theorem_names", [])),
               solution_lines=sum(1 for _ in open(srcf, "rb")) if os.path.exists(srcf) else None,
               system_start=snap(), vm_max_map_count=int(open("/proc/sys/vm/max_map_count").read()))
    if os.environ.get("SKIP_BUILD"):
        rc_b = 0
        rec.update(build_skipped=True, batch=os.environ.get("BATCH_ID"), build_exit=0)
    else:
        bmon = os.path.join(logdir, f"{name}.buildmon")
        rc_b, t_b = run(["python3", "-I", os.path.join(here, "vmamon.py"), "--out", bmon, "--interval", "0.2", "--label", name + "-build", "--",
                         "lake", "build", cfg["challenge_module"], cfg["solution_module"]], os.path.join(logdir, f"{name}.build.driver.log"))
        try:
            bs = json.load(open(os.path.join(bmon, "summary.json")))
            rc_b = bs["exit_code"]
            btext = open(os.path.join(bmon, "stdout.log"), errors="replace").read()
            open(os.path.join(logdir, f"{name}.build.log"), "w").write(btext)
            rec.update(build_peak_vmas=bs["peak_per_process_vmas_sampled"], build_peak_procs=bs["peak_concurrent_processes"],
                       build_peak_proc_rss_gib=round(max([t["max_rss"] for t in bs["top_processes"]] or [0]) / 2**30, 1),
                       build_vmamon_class=bs["classification"], **build_stats(btext))
        except Exception as e:
            rec.update(build_monitor_error=str(e)[:100])
        rec.update(build_exit=rc_b, build_s=round(t_b, 1))
    if rc_b == 0:
        mon = os.path.join(logdir, f"{name}.mon")
        env_path = os.environ["PATH"]
        # vmamon runs INSIDE the sandboxed service so it sees the comparator process tree.
        cmd = ["systemd-run", "--user", "--wait", "--pipe", "--collect", f"--unit=cmp-{name}", "--property=RestrictAddressFamilies=~AF_UNIX",
               *(["--property=MemoryMax=" + os.environ["CHECK_MEMMAX"]] if os.environ.get("CHECK_MEMMAX") else []),
               "-E", f"PATH={env_path}", "-E", f"HOME={os.environ['HOME']}", f"--working-directory={root}",
               *(["taskset", "-c", os.environ["CHECK_CPUS"]] if os.environ.get("CHECK_CPUS") else []),
               "python3", "-I", os.path.join(here, "vmamon.py"), "--out", mon, "--interval", "0.1", "--label", name, "--",
               "lake", "env", comparator, f"ComparatorChallenges/{name}.json"]
        subprocess.run(cmd, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        text = tail(os.path.join(mon, "stdout.log"), 6000)
        try:
            s = json.load(open(os.path.join(mon, "summary.json")))
        except Exception:
            s = {}
        ok = "Your solution is okay!" in text
        m = re.findall(r"uncaught exception: (.*)", text)
        tool_missing = re.findall(r"Failed to find binary: exec: \"(\w+)\"", text)
        tp = (s.get("top_processes") or [{}])[0]
        rec.update(system_end=snap(), cmp_top_process=tp.get("comm"), cmp_cpu_s=s.get("children_cpu_user_s"),
                   export_bytes_total=s.get("export_bytes_total"), export_bytes_largest=s.get("export_bytes_largest"))
        rec.update(cmp_s=s.get("wall_s"), peak_vmas=s.get("peak_per_process_vmas_sampled"),
                   peak_rss_gib=round(max([t["max_rss"] for t in s.get("top_processes", [])] or [0]) / 2**30, 1),
                   vmamon_class=s.get("classification"),
                   outcome="accepted" if ok else ("tool_missing:" + tool_missing[0] if tool_missing else "rejected_or_error"),
                   detail=(m[-1][:300] if m and not ok else ""))
        pre = os.path.join(os.path.dirname(os.path.abspath(out)), "preempted", name)     # set by tools/check_scheduler.py before it stops the unit
        if os.path.exists(pre):
            os.remove(pre); rec.update(outcome="preempted", detail="stopped by check_scheduler under memory pressure; to be re-run")
    else:
        rec.update(outcome="build_failed", detail=tail(os.path.join(logdir, f"{name}.build.log"), 400))
    with open(out, "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(rec["config"], rec["outcome"], rec.get("build_s"), rec.get("cmp_s"), flush=True)
