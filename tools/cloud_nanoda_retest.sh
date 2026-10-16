#!/bin/bash
# cloud_nanoda_retest: run another nanoda build on exports that already exist on the cloud volume, in parallel, then sync the results and power off.
#
# Purpose: nanoda_lib issue 55: the maintainer asked whether upstream master still fails. The laptop retest (tools/nanoda_retest.py) covers what is built there; the Laughlin family
# and the Problem355 declaration need the cloud volume. This runs NANODA on scratch/nanoda-scaling/{Laughlin,LaughlinPlanar,LaughlinFock}.export and scratch/isolate/problem355.export,
# JOBS at a time, 8 threads each, every run in its own systemd unit with a memory cap, no swap and a timeout. One JSON line per run goes to results/nanoda-retest-cloud.jsonl (exit code,
# wall and CPU seconds, peak RSS); results are synced to s3://BUCKET/retest/ and the machine is powered off at the end (behaviour "stop"). A guard shutdown should already be scheduled.
# Usage: cloud_nanoda_retest.sh NANODA_BIN [MEM=55G] [TIMEOUT_S=3600] [BUCKET]
NANODA=$(readlink -f "$1"); MEM=${2:-55G}; TMO=${3:-3600}; BUCKET=${4:-experiment-618-openai-math-a2ea0dcc}
cd "$(dirname "$0")/.." || exit 1
mkdir -p scratch/retest results
run() {  # name export
  n=$1; e=$(readlink -f "$2"); c=scratch/retest/$n.json
  printf '{"use_stdin": false, "export_file_path": "%s", "permitted_axioms": ["propext", "Quot.sound", "Classical.choice"], "unpermitted_axiom_hard_error": true, "num_threads": 8, "nat_extension": true, "string_extension": true}' "$e" > "$c"
  out=$(systemd-run --user --wait --pipe --collect -p MemoryMax=$MEM -p MemorySwapMax=0 -p RuntimeMaxSec=$TMO /usr/bin/time -f 'TIME %e %U %S %M' "$NANODA" "$(readlink -f "$c")" 2>&1); rc=$?
  t=$(echo "$out" | grep '^TIME ' | tail -1)
  python3 - "$n" "$rc" "$t" "$NANODA" "$MEM" <<'PY' >> results/nanoda-retest-cloud.jsonl
import sys, json, subprocess
n, rc, t, nano, mem = sys.argv[1:6]
p = t.split(); w, u, s, m = (float(p[1]), float(p[2]), float(p[3]), int(p[4])) if len(p) == 5 else (None,) * 4
print(json.dumps(dict(config=n, nanoda=nano, mem_cap=mem, nanoda_rc=int(rc), wall_s=w, cpu_s=None if u is None else round(u + s, 1), rss_gib=None if m is None else round(m / 2**20, 2))))
PY
}
run Laughlin scratch/nanoda-scaling/Laughlin.export &
run LaughlinPlanar scratch/nanoda-scaling/LaughlinPlanar.export &
run LaughlinFock scratch/nanoda-scaling/LaughlinFock.export &
run Problem355 scratch/isolate/problem355.export &
wait
date -Is > results/nanoda-retest-cloud.DONE
aws s3 cp results/nanoda-retest-cloud.jsonl s3://$BUCKET/retest/nanoda-retest-cloud.jsonl --only-show-errors
sudo shutdown -h +2 "cloud_nanoda_retest finished"
