#!/bin/bash
# cloud_status.sh HOST [KEY]: one-screen status of a tools/cloud_run.py run on a cloud machine, read over ssh.
# Purpose: supervise the full run from the laptop. Prints the end of the driver log, how many configurations have each outcome, the checks
# running now with their age and memory, load, memory, disk, the build progress line, and the hours the machine has been up (price it by the
# hourly rate of the instance type). Read-only. KEY defaults to ~/.ssh/experiment-pilot.pem.
HOST=${1:?usage: cloud_status.sh HOST [KEY]}; KEY=${2:-$HOME/.ssh/experiment-pilot.pem}
ssh -i "$KEY" -o ConnectTimeout=15 ubuntu@"$HOST" 'cd /home/srv/s/math/openai-math/results/cmp-all 2>/dev/null || exit 3
date -u +"now %FT%TZ, up $(awk "{printf \"%.2f\", \$1/3600}" /proc/uptime) h"
uptime | sed "s/.*load/load/"; grep -E "MemAvailable|SwapFree" /proc/meminfo | tr "\n" " "; echo; df -h / | tail -1
echo "--- driver.log"; tail -6 driver.log | cut -c1-200
echo "--- outcomes (last record per config)"; python3 -I - <<PY
import json, collections
last = {}
for l in open("all.jsonl"):
    if l.strip(): d = json.loads(l); last[d["config"]] = d.get("outcome")
print(len(last), "configs with a record;", dict(collections.Counter(last.values())))
PY
echo "--- running checks"; systemctl --user list-units --no-legend "cmp-*.service" | awk "{print \$1}" | while read u; do s=$(systemctl --user show $u -p ActiveEnterTimestampMonotonic --value); echo "$u $(( ($(awk "{print int(\$1*1e6)}" /proc/uptime) - s) / 60000000 )) min $(systemctl --user show $u -p MemoryCurrent --value | awk "{printf \"%.1f GiB\", \$1/2^30}")"; done
echo "--- builds (priority_build)"; echo "finished $(wc -l < builds.jsonl 2>/dev/null || echo 0) builds, failed: $(grep -c "\"exit\": [1-9]" builds.jsonl 2>/dev/null || echo 0); running: $(ls -t builds/*.log 2>/dev/null | head -0)"; grep -E "build .* modules to compile" driver.log | tail -3 | cut -c1-150
echo "--- phases (nanoda vs Lean kernel) of checks that have reached nanoda or the Lean kernel"
python3 -I - <<PY
import json, datetime, collections
ev = collections.defaultdict(dict)
try:
    for l in open("phases.jsonl"):
        d = json.loads(l); ev[d["config"]][d["event"]] = datetime.datetime.fromisoformat(d["t"])
except FileNotFoundError: pass
now = datetime.datetime.now(datetime.timezone.utc)
import subprocess
act = {l.split()[0][4:-8] for l in subprocess.run(["systemctl", "--user", "list-units", "--no-legend", "cmp-*.service"], capture_output=True, text=True).stdout.splitlines() if l.strip()}
fin = set()
for l in open("all.jsonl"):
    if l.strip(): d = json.loads(l)
    if l.strip() and d.get("outcome") == "accepted": fin.add(d["config"])
for c, e in sorted(ev.items(), key=lambda kv: min(kv[1].values())):
    if c in fin or c not in act: continue
    last = max(e, key=lambda k: e[k]); na = e.get("nanoda_accepts") or e.get("nanoda_rejected")
    ndur = f"nanoda {int((na - e[chr(110)+'anoda_start']).total_seconds())} s ({chr(111)+'k' if 'nanoda_accepts' in e else 'REJECTED'})" if na and "nanoda_start" in e else "nanoda running" if "nanoda_start" in e else "exporting"
    print(f"{c:28s} {ndur:28s} last event {last} {int((now - e[last]).total_seconds()/60)} min ago")
PY
ls DONE 2>/dev/null'
