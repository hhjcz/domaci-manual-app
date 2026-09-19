#!/usr/bin/env bash
# Refresh the baked-in GitHub SSH host keys from GitHub's published metadata.
set -euo pipefail
cd "$(dirname "$0")/.."
target=domaci_manual/rootfs/usr/share/domaci-manual/known_hosts
{
  echo "# GitHub SSH host keys, from https://api.github.com/meta (ssh_keys)."
  echo "# Refresh with: scripts/update_known_hosts.sh"
  curl -fsS https://api.github.com/meta | python3 -c "
import sys, json
keys = json.load(sys.stdin)['ssh_keys']
for host in ('github.com', 'ssh.github.com'):
    for key in keys:
        print(f'{host} {key}')
"
} > "$target"
echo "Wrote $target"
