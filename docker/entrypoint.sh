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
#
# Claude Code's built-in Bash sandbox (#1028) is configured through managed
# settings written here on every boot (docker/lib/gen-managed-settings.sh):
#   CLAUDE_SANDBOX=0          write an explicit off (default: on)
#   CLAUDE_CREDENTIAL_MASK=1  mask GARMIN_PASSWORD / GITHUB_TOKEN for sandboxed
#                             commands (default: off — see docker/README.md)
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

  # Can bubblewrap create a user namespace as the claude user? Under Docker's
  # default seccomp + AppArmor and Ubuntu's apparmor_restrict_unprivileged_userns
  # it cannot, and then Claude Code does NOT fall back: with bwrap installed,
  # every sandboxed Bash command fails with the bwrap error. So the policy is
  # only enabled when the probe passes (docker/README.md, "Why it still falls
  # back"; sandbox-smoke.sh prints the exact blocker).
  if setpriv --reuid "$uid" --regid "$gid" --init-groups -- \
       bwrap --unshare-user --ro-bind / / --dev /dev --bind /proc /proc true 2>/dev/null; then
    export SANDBOX_USERNS_OK=1
  else
    export SANDBOX_USERNS_OK=0
    echo "INFO: bubblewrap cannot create a user namespace in this container —" >&2
    echo "      writing Claude Code sandbox.enabled=false (Docker stays the boundary)." >&2
  fi

  # Managed settings are the only tier Claude Code honours for credential masking
  # and they win over the bind-mounted project/user settings, so the policy is
  # container-only and repo-controlled. Root-owned, world-readable.
  bash /usr/local/lib/sandbox/gen-managed-settings.sh \
      /etc/sandbox/allowed-domains.txt /etc/claude-code/managed-settings.json
  # setpriv (unlike `su -`/`login`) does NOT reset HOME, so it would stay /root
  # (root-owned, unwritable post-drop) and bash would read /root/.bashrc while
  # uv/npm caches landed in /root/.cache — both Permission denied. Set HOME (and
  # USER/LOGNAME) to claude's explicitly. We do this by export rather than
  # `setpriv --reset-env` because --reset-env clears every env var except TERM,
  # which would wipe the --env-file vars (GARMIN_*, creds) and Dockerfile ENV
  # (UV_PROJECT_ENVIRONMENT etc.) that MCP auth and the venv location depend on.
  HOME="$(getent passwd "$uid" | cut -d: -f6)"
  export HOME USER=claude LOGNAME=claude
  # Drop root → claude (root dropping privileges is always allowed, even under
  # no-new-privileges) and run the requested command.
  exec setpriv --reuid "$uid" --regid "$gid" --init-groups -- "$@"
fi

# Already unprivileged (e.g. re-exec); just run the command.
exec "$@"
