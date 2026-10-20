#!/bin/bash
# overnight.sh: run Comparator on every OpenAI/math config, one at a time, smallest solution closure first.
# Resumable (results/cmp-all/all.jsonl; configs already accepted are skipped), pauses cleanly if
# results/cmp-all/STOP exists, archives generated C files (compress, verify, then remove) whenever free
# disk < SWEEP_GIB, and halts with results/cmp-all/ALERT if disk cannot be recovered. Uses no model tokens.
# Start: tmux new -d -s overnight tools/overnight.sh     Pause: touch results/cmp-all/STOP     Resume: rm STOP, rerun.
base=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd); R=$base/results/cmp-all; mkdir -p $R
export PATH=$base/ext/bin:$base/ext/lean4export/.lake/build/bin:$HOME/.elan/bin:$PATH
SWEEP_GIB=${SWEEP_GIB:-65}; MIN_GIB=${MIN_GIB:-35}
cd $base
# seed with earlier accepted results so they are not redone
python3 - "$base" <<'P'
import json,os,sys
base=sys.argv[1]; out=base+'/results/cmp-all/all.jsonl'
have={json.loads(l)['config'] for l in open(out)} if os.path.exists(out) else set()
with open(out,'a') as f:
    for src in ('results/cmp-batch/pilot.jsonl','results/cmp-cubic/cubic.jsonl'):
        if os.path.exists(base+'/'+src):
            for l in open(base+'/'+src):
                d=json.loads(l)
                if d.get('outcome')=='accepted' and d['config'] not in have:
                    d['seeded_from']=src; f.write(json.dumps(d)+'\n'); have.add(d['config'])
P
# wait for any running pilot batch (single Lake workspace, no concurrent builds)
while pgrep -f 'run_comparator_batch.py.*pilot.jsonl' >/dev/null; do sleep 30; done
free_gib() { df -BG --output=avail /home | tail -1 | tr -dc 0-9; }
sweep() {
  ts=$(date +%Y%m%dT%H%M%S)
  dirs=$(cd $base/src/lean/.lake/build && ls -d ir/OAI/* ir/ComparatorChallenges 2>/dev/null)
  [ -n "$dirs" ] && $base/tools/archive_ir.sh sweep-$ts $dirs >> $R/sweep.log 2>&1
}
is_done() { python3 - "$1" "$R" <<'P'
import json,sys
n=sys.argv[1]
ok=any(json.loads(l)['config']==n and json.loads(l)['outcome']=='accepted' for l in open(sys.argv[2]+'/all.jsonl'))
sys.exit(0 if ok else 1)
P
}
ORDER=$base/results/config-order.json; [ -f $ORDER ] || ORDER=$base/results/config-solution-size.json
for name in $(python3 -c "
import json
d=json.load(open('$ORDER'))
for x in d: print(x if isinstance(x,str) else x[1])"); do
  [ -e $R/STOP ] && { echo "$(date -Is) STOP file found; exiting cleanly" >> $R/driver.log; exit 0; }
  is_done $name && continue
  [ "$(free_gib)" -lt $SWEEP_GIB ] && sweep
  if [ "$(free_gib)" -lt $MIN_GIB ]; then echo "disk $(free_gib)G < ${MIN_GIB}G after sweep, halting $(date -Is)" | tee $R/ALERT >> $R/driver.log; exit 2; fi
  echo "$(date -Is) restore: $(python3 -I $base/tools/restore_ir_for.py $base/src/lean $name 2>&1 | tail -1)" >> $R/driver.log
  echo "$(date -Is) start $name free=$(free_gib)G" >> $R/driver.log
  python3 -I $base/tools/run_comparator_batch.py $base/src/lean $R/all.jsonl $name >> $R/driver.log 2>&1
done
echo "$(date -Is) all configs attempted" >> $R/driver.log
