#!/usr/bin/env bash
#
# Post-boot smoke test for the sandbox container, run as the unprivileged `claude`
# user AFTER entrypoint.sh installed the firewall. Proves the egress gate from the
# inside: allowlisted names resolve and connect, everything else is refused at the
# resolver and at the packet filter.
#
# Used by CI (docker-build job) and by the owner after a rebuild:
#   docker/run.sh sandbox-smoke.sh
#
# Exit 0 if every check passes; prints the failing checks and exits 1 otherwise.
set -uo pipefail

failures=0
ok()   { echo "  ok:   $*"; }
fail() { echo "  FAIL: $*" >&2; failures=$((failures + 1)); }

http_code() {
    # 000 = no TCP/TLS connection at all (refused / dropped / unresolved).
    curl -s -o /dev/null -w '%{http_code}' --connect-timeout 8 "https://$1" 2>/dev/null || echo 000
}

echo "Sandbox smoke test"

# --- resolver -------------------------------------------------------------
if grep -q '^nameserver 127\.0\.0\.1$' /etc/resolv.conf; then
    ok "resolver is dnsmasq on 127.0.0.1"
else
    fail "/etc/resolv.conf does not point at 127.0.0.1"
fi

if getent hosts pypi.org >/dev/null; then
    ok "allowlisted name resolves (pypi.org)"
else
    fail "pypi.org does not resolve"
fi

if getent hosts example.com >/dev/null; then
    fail "unlisted name resolves (example.com) — dnsmasq is not allowlist-only"
else
    ok "unlisted name is refused (example.com)"
fi

if dig +short +time=2 +tries=1 example.com @1.1.1.1 >/dev/null 2>&1; then
    fail "direct DNS to 1.1.1.1 succeeded — port 53 is open to arbitrary hosts"
else
    ok "direct DNS to a foreign resolver is rejected"
fi

# --- packet filter ----------------------------------------------------------
if timeout 3 bash -c 'echo >/dev/tcp/1.1.1.1/22' 2>/dev/null; then
    fail "tcp/22 to a non-allowlisted host succeeded"
else
    ok "tcp/22 to a non-allowlisted host is rejected"
fi

if timeout 3 bash -c 'echo >/dev/tcp/93.184.215.14/443' 2>/dev/null; then
    fail "direct connection to a non-allowlisted IP succeeded"
else
    ok "direct connection to a non-allowlisted IP is rejected"
fi

# --- reachability of what the toolchain needs --------------------------------
for host in api.github.com pypi.org registry.npmjs.org connect.garmin.com; do
    code=$(http_code "$host")
    if [ "$code" != "000" ]; then
        ok "$host reachable (HTTP $code)"
    else
        fail "$host unreachable"
    fi
done

# --- documentation tier (the WebFetch case that motivated #1027) ------------
for host in duckdb.org developer.garmin.com; do
    code=$(http_code "$host")
    if [ "$code" != "000" ]; then
        ok "docs tier: $host reachable (HTTP $code)"
    else
        fail "docs tier: $host unreachable"
    fi
done

# --- Claude Code built-in sandbox: pinned OFF (#1033) -------------------------
# The bind-mounted .claude/settings.local.json says sandbox.enabled=true (saved on
# the host). Inside the container that must never take effect: bubblewrap is not
# installed and could not create a user namespace here anyway, and with bwrap
# present-but-failing every sandboxed Bash command errors (#1032). The static
# managed-settings file overrides the project setting.
ms=/etc/claude-code/managed-settings.json
if [ -r "$ms" ] && [ "$(jq -r '.sandbox.enabled' "$ms" 2>/dev/null)" = "false" ]; then
    ok "built-in Claude sandbox pinned off by managed settings (Docker is the boundary)"
else
    fail "managed settings missing or not pinning the built-in sandbox off at $ms"
fi
if command -v bwrap >/dev/null 2>&1; then
    fail "bubblewrap is installed — a present-but-failing bwrap breaks every sandboxed Bash command (#1032)"
else
    ok "bubblewrap not installed (nothing for a stray sandbox.enabled=true to break)"
fi

echo
if [ "$failures" -eq 0 ]; then
    echo "Sandbox smoke test: all checks passed"
    exit 0
fi
echo "Sandbox smoke test: $failures check(s) FAILED" >&2
exit 1
