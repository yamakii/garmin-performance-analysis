#!/bin/bash
#
# Egress allowlist firewall for the Claude Code sandbox container.
#
# Default-DROP outbound traffic; only an explicit allowlist of hosts is reachable.
# This is what makes `dangerouslyDisableSandbox` acceptable inside the container:
# even if a dependency (PyPI / npm / serena git) or a prompt-injection runs code,
# it cannot POST the mounted secrets (.env Garmin creds, GITHUB_TOKEN, Claude
# credentials) to an arbitrary host.
#
# Based on anthropics/claude-code/.devcontainer/init-firewall.sh, extended with
# the hosts this project needs (PyPI, Garmin, GitHub Copilot MCP, Anthropic auth)
# and with per-domain resolution failures downgraded to warnings so a transient
# DNS hiccup on one host does not block container startup.
#
# Run as root with NET_ADMIN + NET_RAW (entrypoint.sh handles this).
set -euo pipefail
IFS=$'\n\t'

# 1. Extract Docker's embedded-DNS NAT rules BEFORE flushing, so name resolution
#    keeps working after we reset the tables.
DOCKER_DNS_RULES=$(iptables-save -t nat | grep "127\.0\.0\.11" || true)

# Flush existing rules and ipsets.
iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X
iptables -t mangle -F
iptables -t mangle -X
ipset destroy allowed-domains 2>/dev/null || true

# 2. Restore ONLY the internal Docker DNS resolution NAT rules.
if [ -n "$DOCKER_DNS_RULES" ]; then
    echo "Restoring Docker DNS rules..."
    iptables -t nat -N DOCKER_OUTPUT 2>/dev/null || true
    iptables -t nat -N DOCKER_POSTROUTING 2>/dev/null || true
    echo "$DOCKER_DNS_RULES" | xargs -L 1 iptables -t nat
else
    echo "No Docker DNS rules to restore"
fi

# Allow DNS + loopback + SSH before any restrictions.
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A INPUT  -p udp --sport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 22 -j ACCEPT
iptables -A INPUT  -p tcp --sport 22 -m state --state ESTABLISHED -j ACCEPT
iptables -A INPUT  -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

ipset create allowed-domains hash:net

# --- GitHub IP ranges (covers github.com / api.github.com / git over https) ---
echo "Fetching GitHub IP ranges..."
gh_ranges=$(curl -s --connect-timeout 10 https://api.github.com/meta || true)
if [ -z "$gh_ranges" ] || ! echo "$gh_ranges" | jq -e '.web and .api and .git' >/dev/null 2>&1; then
    echo "ERROR: failed to fetch usable GitHub IP ranges from api.github.com/meta" >&2
    exit 1
fi
echo "Processing GitHub IP ranges..."
while read -r cidr; do
    [[ "$cidr" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}/[0-9]{1,2}$ ]] || continue
    ipset add allowed-domains "$cidr" 2>/dev/null || true
done < <(echo "$gh_ranges" | jq -r '(.web + .api + .git)[]' | aggregate -q)

# --- Other allowed domains (resolved at startup) ---
# Anthropic API + auth (subscription OAuth refresh may use claude.ai / console).
# PyPI for `uv sync`. npm registry. GitHub Copilot endpoint for the github MCP.
# Garmin for garmin-db ingest. Telemetry hosts are harmless if present.
for domain in \
    "api.anthropic.com" \
    "claude.ai" \
    "console.anthropic.com" \
    "statsig.anthropic.com" \
    "sentry.io" \
    "statsig.com" \
    "registry.npmjs.org" \
    "pypi.org" \
    "files.pythonhosted.org" \
    "api.githubcopilot.com" \
    "objects.githubusercontent.com" \
    "codeload.github.com" \
    "connect.garmin.com" \
    "connectapi.garmin.com" \
    "sso.garmin.com" \
    "diauth.garmin.com" ; do
    echo "Resolving $domain..."
    ips=$(dig +noall +answer A "$domain" | awk '$4 == "A" {print $5}')
    if [ -z "$ips" ]; then
        # Non-fatal: a single unresolved host should not block startup. The user
        # will see connection errors for that service and can extend the list.
        echo "WARN: could not resolve $domain — skipping (extend allowlist if a service needs it)" >&2
        continue
    fi
    while read -r ip; do
        [[ "$ip" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]] || continue
        ipset add allowed-domains "$ip" 2>/dev/null || true
    done < <(echo "$ips")
done

# Allow the local Docker host network (gateway, embedded DNS).
HOST_IP=$(ip route | grep default | cut -d" " -f3)
if [ -n "$HOST_IP" ]; then
    HOST_NETWORK=$(echo "$HOST_IP" | sed "s/\.[0-9]*$/.0\/24/")
    echo "Host network detected as: $HOST_NETWORK"
    iptables -A INPUT  -s "$HOST_NETWORK" -j ACCEPT
    iptables -A OUTPUT -d "$HOST_NETWORK" -j ACCEPT
fi

# Default-DROP, then allow established + the allowlist set.
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT DROP
iptables -A INPUT  -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m set --match-set allowed-domains dst -j ACCEPT
iptables -A OUTPUT -j REJECT --reject-with icmp-admin-prohibited

# --- self-verification ---
echo "Verifying firewall rules..."
if curl --connect-timeout 5 -s https://example.com >/dev/null 2>&1; then
    echo "ERROR: firewall verification FAILED — example.com is reachable (egress not locked down)" >&2
    exit 1
fi
echo "  OK: example.com is blocked as expected"
if ! curl --connect-timeout 5 -s https://api.github.com/zen >/dev/null 2>&1; then
    echo "ERROR: firewall verification FAILED — api.github.com is NOT reachable" >&2
    exit 1
fi
echo "  OK: api.github.com is reachable as expected"
echo "Firewall configuration complete."
