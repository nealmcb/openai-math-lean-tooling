#!/bin/bash
# with_maxmap.sh N cmd...: set vm.max_map_count=N (via the narrow sudoers rule), run cmd, ALWAYS restore the old value.
old=$(cat /proc/sys/vm/max_map_count); trap 'sudo -n /usr/sbin/sysctl -w vm.max_map_count=$old >/dev/null' EXIT INT TERM
sudo -n /usr/sbin/sysctl -w vm.max_map_count=$1 >/dev/null || exit 99; shift; "$@"
