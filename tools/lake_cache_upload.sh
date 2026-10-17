#!/bin/bash
# lake_cache_upload.sh LAKECACHE_DIR BUCKET SCOPE REV: publish a converted Lake cache (from lake_cache_convert.py) to Cloudflare R2 with rclone, credentials from ~/.r2env (see push_r2_env.sh).
# Purpose: lay out the files as Lake's custom-endpoint cache expects: artifacts a/SCOPE/HASH.art (hardlinks of cache/artifacts/HASH.ltar, only those named in map-all.jsonl) and the mapping r/SCOPE/REV.jsonl,
# where REV is the Git commit of the OAI checkout. Artifacts go first, the mapping last, so a consumer never sees a mapping that points to missing files. Never prints credentials.
set -eu
D=$(realpath "${1:?dir}"); BUCKET=${2:?bucket}; SCOPE=${3:?scope}; REV=${4:?rev}; . ~/.r2env; export PATH=$HOME/bin:$PATH
S="$D/stage"; rm -rf "$S"; mkdir -p "$S/a/$SCOPE" "$S/r/$SCOPE"
python3 -I - "$D" "$S/a/$SCOPE" <<'PY'
import sys, os, json
d, dst = sys.argv[1:]
for l in open(os.path.join(d, 'map-all.jsonl')):
    if l.startswith('['):
        v = json.loads(l)[1]; os.link(os.path.join(d, 'cache/artifacts', v), os.path.join(dst, v[:-5] + '.art'))
PY
cp "$D/map-all.jsonl" "$S/r/$SCOPE/$REV.jsonl"; echo "staged $(ls "$S/a/$SCOPE" | wc -l) artifacts"
time rclone copy "$S/a" r2:$BUCKET/a --s3-no-check-bucket --transfers 64 --checkers 64 --stats 30s --stats-one-line -v 2>&1 | grep -vi "copied\|not updating" | tail -5
rclone copy "$S/r" r2:$BUCKET/r --s3-no-check-bucket -v 2>&1 | tail -2
echo "uploaded"
