#!/usr/bin/env bash
# Generate Claude Code managed settings for the sandbox container (#1028).
#
# Managed settings (/etc/claude-code/managed-settings.json) are the only tier
# where Claude Code honours `sandbox.credentials` masking and
# `network.tlsTerminate` (repository settings are ignored for those), and their
# booleans win over the bind-mounted project/user settings. Writing the file from
# the entrypoint gives the container a sandbox policy that is repo-controlled,
# container-only, and regenerated on every boot from the environment.
#
# Sourced by scripts/tests/test-sandbox-managed-settings.sh (pure function, no
# root) and executed by entrypoint.sh as root:
#     gen-managed-settings.sh ALLOWLIST_FILE OUTPUT_FILE
#
# Environment:
#   CLAUDE_SANDBOX=1|0          default 1. Enable Claude Code's built-in Bash
#                               sandbox (bubblewrap + socat are in the image).
#                               0 writes an explicit off.
#   CLAUDE_CREDENTIAL_MASK=1|0  default 0. Mask GARMIN_PASSWORD / GITHUB_TOKEN for
#                               sandboxed commands: they see a placeholder and the
#                               sandbox proxy injects the real value only towards
#                               the listed hosts. Requires TLS termination at the
#                               proxy — see docker/README.md before enabling.
#   GARMIN_DATA_DIR, GARMIN_RESULT_DIR, GARMINTOKENS
#                               added to filesystem.allowWrite when set.
#   SANDBOX_HOME                default /home/claude (the claude user's home).

# shellcheck source=allowlist.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/allowlist.sh"

# gen_managed_settings ALLOWLIST_FILE
# Prints the managed-settings JSON on stdout. Exits 1 on an invalid allowlist.
gen_managed_settings() {
  local allowlist="$1"
  local home="${SANDBOX_HOME:-/home/claude}"

  if [ "${CLAUDE_SANDBOX:-1}" != "1" ]; then
    printf '{"sandbox":{"enabled":false}}\n'
    return 0
  fi

  local domains
  domains="$(allowlist_domains "$allowlist")" || return 1

  # Every allowlist entry means "domain + subdomains" (dnsmasq suffix match), so
  # mirror it for the sandbox proxy as the apex plus a wildcard.
  local allowed_json
  allowed_json="$(printf '%s\n' "$domains" \
    | jq -R -s 'split("\n") | map(select(length > 0)) | map(., "*." + .)')"

  # Paths sandboxed commands must write outside the working directory: the uv
  # venv (UV_PROJECT_ENVIRONMENT), tool caches, Claude's own job/memory dirs, and
  # the data/result/token dirs the MCP scripts populate.
  local -a writes=(
    "$home/uv-venv"
    "$home/.cache"
    "$home/.npm"
    "$home/.claude/jobs"
    "$home/.claude/projects"
    "/tmp"
  )
  local v
  for v in GARMIN_DATA_DIR GARMIN_RESULT_DIR GARMINTOKENS; do
    [ -n "${!v:-}" ] && writes+=("${!v}")
  done
  local writes_json
  writes_json="$(printf '%s\n' "${writes[@]}" \
    | jq -R -s 'split("\n") | map(select(length > 0)) | unique')"

  jq -n \
    --argjson allowed "$allowed_json" \
    --argjson writes "$writes_json" \
    --arg mask "${CLAUDE_CREDENTIAL_MASK:-0}" '
    ($mask == "1") as $mask
    | {
        sandbox: (
          {
            enabled: true,
            # bubblewrap cannot mount a fresh /proc under --cap-drop ALL + the
            # Docker default seccomp profile; the outer container is the boundary.
            enableWeakerNestedSandbox: true,
            autoAllowBashIfSandboxed: true,
            filesystem: { allowWrite: $writes },
            network: (
              { allowedDomains: $allowed }
              + (if $mask then { tlsTerminate: {} } else {} end)
            )
          }
          + (if $mask then {
              credentials: {
                envVars: [
                  { name: "GARMIN_PASSWORD", mode: "mask",
                    injectHosts: ["sso.garmin.com", "diauth.garmin.com",
                                  "connect.garmin.com", "connectapi.garmin.com"] },
                  { name: "GITHUB_TOKEN", mode: "mask",
                    injectHosts: ["api.github.com", "github.com"] }
                ]
              }
            } else {} end)
        )
      }'
}

# Executed (not sourced): write the file atomically.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  set -euo pipefail
  if [ $# -ne 2 ]; then
    echo "usage: $0 ALLOWLIST_FILE OUTPUT_FILE" >&2
    exit 2
  fi
  mkdir -p "$(dirname "$2")"
  gen_managed_settings "$1" >"$2.tmp"
  chmod 644 "$2.tmp"
  mv "$2.tmp" "$2"
fi
