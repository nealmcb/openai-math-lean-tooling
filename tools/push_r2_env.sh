#!/bin/bash
# push_r2_env.sh HOST [KEY] [REMOTE]: copy the R2 credentials of the local rclone remote REMOTE (default r2) to HOST as ~/.r2env (mode 600), without printing them.
# Purpose: let a cloud instance upload to Cloudflare R2 with rclone, taking the settings from environment variables (`. ~/.r2env`), so no rclone config file is needed there.
# Afterwards, `. ~/.r2env; rclone lsd r2:` lists the buckets. Delete it when done: ssh HOST rm ~/.r2env (and roll the R2 token in the Cloudflare dashboard if you want it dead).
HOST=${1:?usage: push_r2_env.sh HOST [KEY] [REMOTE]}; KEY=${2:-$HOME/.ssh/experiment-pilot.pem}; REMOTE=${3:-r2}
get() { rclone config show "$REMOTE" 2>/dev/null | sed -n "s/^$1 *= *//p" | head -1; }
ID=$(get access_key_id); SECRET=$(get secret_access_key); EP=$(get endpoint)
[ -n "$ID" ] && [ -n "$SECRET" ] && [ -n "$EP" ] || { echo "could not read access_key_id/secret_access_key/endpoint of remote $REMOTE" >&2; exit 1; }
printf 'export RCLONE_CONFIG_R2_TYPE=s3\nexport RCLONE_CONFIG_R2_PROVIDER=Cloudflare\nexport RCLONE_CONFIG_R2_ACCESS_KEY_ID=%s\nexport RCLONE_CONFIG_R2_SECRET_ACCESS_KEY=%s\nexport RCLONE_CONFIG_R2_ENDPOINT=%s\n' "$ID" "$SECRET" "$EP" |
  ssh -i "$KEY" ubuntu@"$HOST" 'umask 077; cat > ~/.r2env'
echo "wrote ~/.r2env on $HOST: id ${#ID} chars, secret ${#SECRET} chars, endpoint ${#EP} chars"
