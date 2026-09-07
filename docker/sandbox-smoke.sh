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

# --- Claude Code built-in sandbox (#1028) -----------------------------------
warn() { echo "  warn: $*"; }

if command -v bwrap >/dev/null && command -v socat >/dev/null; then
    ok "bubblewrap + socat present (built-in sandbox can start)"
else
    fail "bubblewrap/socat missing — Claude Code's built-in sandbox silently falls back"
fi

ms=/etc/claude-code/managed-settings.json
if [ -r "$ms" ] && jq -e '.sandbox | has("enabled")' "$ms" >/dev/null 2>&1; then
    ok "managed settings present (sandbox.enabled=$(jq -c '.sandbox.enabled' "$ms"))"
    if jq -e '.sandbox.enabled == true' "$ms" >/dev/null; then
        # shellcheck source=lib/allowlist.sh
        . /usr/local/lib/sandbox/allowlist.sh
        n_list=$(allowlist_domains /etc/sandbox/allowed-domains.txt | wc -l)
        n_allow=$(jq '.sandbox.network.allowedDomains | length' "$ms")
        if [ "$n_allow" -eq $((n_list * 2)) ]; then
            ok "sandbox allowedDomains mirror the allowlist ($n_list domains → $n_allow entries)"
        else
            fail "sandbox allowedDomains ($n_allow) do not mirror the allowlist ($n_list domains)"
        fi
        if jq -e '.sandbox.filesystem.allowWrite | index("/home/claude/uv-venv")' "$ms" >/dev/null; then
            ok "sandbox allowWrite covers the uv venv"
        else
            fail "sandbox allowWrite misses /home/claude/uv-venv (uv sync would fail)"
        fi
        # Namespaces are what bubblewrap needs; under --cap-drop ALL + the Docker
        # default seccomp profile this may be refused, in which case Claude Code
        # falls back to unsandboxed Bash (Docker stays the boundary). Informational.
        if bwrap --unshare-user --ro-bind / / --dev /dev --proc /proc true 2>/dev/null; then
            ok "bubblewrap can create namespaces here (fresh /proc works)"
        elif bwrap --unshare-user --ro-bind / / --dev /dev --bind /proc /proc true 2>/dev/null; then
            ok "bubblewrap can create namespaces here (needs enableWeakerNestedSandbox, which is set)"
        else
            warn "bubblewrap cannot create namespaces in this container — Claude Code will fall back to unsandboxed Bash"
        fi
    fi
else
    fail "managed settings missing or invalid at $ms"
fi

echo
if [ "$failures" -eq 0 ]; then
    echo "Sandbox smoke test: all checks passed"
    exit 0
fi
echo "Sandbox smoke test: $failures check(s) FAILED" >&2
exit 1
