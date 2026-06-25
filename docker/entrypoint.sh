#!/usr/bin/env bash
#
# Container entrypoint.
#
# The container starts as root so we can install the egress firewall, then drops
# to the unprivileged `claude` user before running the requested command (CMD,
# default: bash). This is the only point at which root privileges are used.
#
# Set SANDBOX_FIREWALL=0 to start WITHOUT the egress allowlist (debugging only —
# this removes the exfiltration protection that makes dangerouslyDisableSandbox
# acceptable inside the container).
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
  if [ "${SANDBOX_FIREWALL:-1}" = "1" ]; then
    if ! /usr/local/bin/init-firewall.sh; then
      echo "FATAL: egress firewall setup failed — refusing to start with an open network." >&2
      echo "       (override with SANDBOX_FIREWALL=0 for debugging, at your own risk)" >&2
      exit 1
    fi
  else
    echo "WARN: SANDBOX_FIREWALL=0 — starting WITHOUT the egress allowlist (network is open)." >&2
  fi

  uid="$(id -u claude)"
  gid="$(id -g claude)"
  # Drop root → claude (root dropping privileges is always allowed, even under
  # no-new-privileges) and run the requested command.
  exec setpriv --reuid "$uid" --regid "$gid" --init-groups -- "$@"
fi

# Already unprivileged (e.g. re-exec); just run the command.
exec "$@"
