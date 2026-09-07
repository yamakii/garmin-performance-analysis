#!/bin/bash
#
# Egress allowlist firewall for the Claude Code sandbox container.
#
# Default-DROP outbound traffic; only the domains listed in docker/allowed-domains.txt
# (baked into the image at /etc/sandbox/allowed-domains.txt) are reachable. This is
# what makes `dangerouslyDisableSandbox` acceptable inside the container: even if a
# dependency (PyPI / npm / serena git) or a prompt-injection runs code, it cannot
# POST the mounted secrets (.env Garmin creds, GITHUB_TOKEN, Claude credentials) to
# an arbitrary host.
#
# DNS is the gate:
#   1. dnsmasq is the container's only resolver (/etc/resolv.conf → 127.0.0.1). It
#      forwards ONLY allowlisted names to the upstream resolver and adds every IPv4
#      it returns to the `allowed-domains` ipset at resolution time — so CDN IP
#      rotation mid-session is handled, and no client needs a proxy setting
#      (WebFetch, the MCP servers, uv, git all work unchanged).
#   2. Unlisted names are refused locally: they never reach the upstream resolver
#      (no DNS tunnelling) and never obtain an IP to connect to.
#   3. iptables OUTPUT accepts loopback, dnsmasq's own upstream queries (matched by
#      uid), the Docker host network, established flows and the ipset. Everything
#      else is rejected — including port 53 / 22 towards arbitrary hosts.
#
# Originally based on anthropics/claude-code/.devcontainer/init-firewall.sh. Its
# startup-time resolution and api.github.com/meta CIDR prefetch were replaced by the
# dnsmasq gate (#1027): an IP-only allowlist let CDN neighbours of allowed hosts
# through while blocking listed hosts once their IPs rotated, and the /meta fetch
# had its own rate-limit fail-closed mode.
#
# Run as root with NET_ADMIN + NET_RAW (entrypoint.sh handles this).
set -euo pipefail
IFS=$'\n\t'

ALLOWLIST="${SANDBOX_ALLOWLIST:-/etc/sandbox/allowed-domains.txt}"
SANDBOX_STATE=/run/sandbox
DNSMASQ_CONF="$SANDBOX_STATE/dnsmasq.conf"
DNSMASQ_PID="$SANDBOX_STATE/dnsmasq.pid"
UPSTREAMS_FILE="$SANDBOX_STATE/upstreams"
# Dedicated unprivileged user for the resolver; created in the Dockerfile. iptables
# matches its uid to let ONLY dnsmasq talk to the upstream resolver.
DNSMASQ_USER=dnsmasq

# shellcheck source=lib/allowlist.sh
. /usr/local/lib/sandbox/allowlist.sh

mkdir -p "$SANDBOX_STATE"

# 1. Capture the upstream resolvers + Docker's embedded-DNS NAT rules BEFORE we
#    touch anything. dnsmasq forwards to the upstreams; the NAT rules keep
#    127.0.0.11 working on user-defined Docker networks. On a re-run inside a
#    running container resolv.conf already points at us, so fall back to the
#    upstreams recorded by the first run.
mapfile -t UPSTREAMS < <(awk '$1 == "nameserver" && $2 != "127.0.0.1" {print $2}' /etc/resolv.conf)
if [ "${#UPSTREAMS[@]}" -eq 0 ] && [ -s "$UPSTREAMS_FILE" ]; then
    mapfile -t UPSTREAMS <"$UPSTREAMS_FILE"
fi
if [ "${#UPSTREAMS[@]}" -eq 0 ]; then
    echo "ERROR: no upstream nameserver found in /etc/resolv.conf" >&2
    exit 1
fi
printf '%s\n' "${UPSTREAMS[@]}" >"$UPSTREAMS_FILE"
DOCKER_DNS_RULES=$(iptables-save -t nat | grep "127\.0\.0\.11" || true)

# Flush existing rules and ipsets.
iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X
iptables -t mangle -F
iptables -t mangle -X
ipset destroy allowed-domains 2>/dev/null || true
ipset create allowed-domains hash:net

# Restore ONLY the internal Docker DNS resolution NAT rules.
if [ -n "$DOCKER_DNS_RULES" ]; then
    echo "Restoring Docker DNS rules..."
    iptables -t nat -N DOCKER_OUTPUT 2>/dev/null || true
    iptables -t nat -N DOCKER_POSTROUTING 2>/dev/null || true
    echo "$DOCKER_DNS_RULES" | xargs -L 1 iptables -t nat
else
    echo "No Docker DNS rules to restore"
fi

# 2. dnsmasq: allowlist-only forwarding, feeding the ipset.
echo "Starting dnsmasq (upstreams: ${UPSTREAMS[*]})..."
dnsmasq_conf "$ALLOWLIST" "${UPSTREAMS[@]}" >"$DNSMASQ_CONF"
if [ -f "$DNSMASQ_PID" ]; then
    kill "$(cat "$DNSMASQ_PID")" 2>/dev/null || true
    rm -f "$DNSMASQ_PID"
fi
# dnsmasq drops to $DNSMASQ_USER itself and keeps CAP_NET_ADMIN for the ipset feed.
dnsmasq --conf-file="$DNSMASQ_CONF" --user="$DNSMASQ_USER" --pid-file="$DNSMASQ_PID"
# /etc/resolv.conf is a Docker-managed bind mount, writable by root in the container.
printf 'nameserver 127.0.0.1\noptions ndots:0\n' >/etc/resolv.conf

# 3. iptables: loopback + DNS first.
iptables -A INPUT  -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT
# Only dnsmasq may talk to the upstream resolver. Every other process is refused
# at port 53 (it reaches dnsmasq through 127.0.0.1 via the loopback rule above),
# which closes direct DNS tunnelling to arbitrary hosts.
iptables -A OUTPUT -p udp --dport 53 -m owner --uid-owner "$DNSMASQ_USER" -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -m owner --uid-owner "$DNSMASQ_USER" -j ACCEPT
iptables -A OUTPUT -p udp --dport 53 -j REJECT
iptables -A OUTPUT -p tcp --dport 53 -j REJECT

# Allow the local Docker host network (gateway, embedded DNS).
HOST_IP=$(ip route | grep default | cut -d" " -f3)
if [ -n "$HOST_IP" ]; then
    HOST_NETWORK=$(echo "$HOST_IP" | sed "s/\.[0-9]*$/.0\/24/")
    echo "Host network detected as: $HOST_NETWORK"
    iptables -A INPUT  -s "$HOST_NETWORK" -j ACCEPT
    iptables -A OUTPUT -d "$HOST_NETWORK" -j ACCEPT
fi

# Default-DROP, then allow established + the allowlist set (every port: the set only
# ever holds IPs of allowlisted names, so git-over-ssh to github.com still works).
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT DROP
iptables -A INPUT  -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m set --match-set allowed-domains dst -j ACCEPT
iptables -A OUTPUT -j REJECT --reject-with icmp-admin-prohibited

# --- self-verification (fail-closed: any failure aborts container start) ---
echo "Verifying firewall rules..."
if [ -n "$(dig +short +time=2 +tries=1 example.com @127.0.0.1 2>/dev/null)" ]; then
    echo "ERROR: firewall verification FAILED — example.com resolves (dnsmasq is not allowlist-only)" >&2
    exit 1
fi
echo "  OK: example.com is refused by the resolver as expected"
if curl --connect-timeout 5 -s https://example.com >/dev/null 2>&1; then
    echo "ERROR: firewall verification FAILED — example.com is reachable (egress not locked down)" >&2
    exit 1
fi
echo "  OK: example.com is unreachable as expected"
gh_ip=$(dig +short +time=3 +tries=2 api.github.com @127.0.0.1 | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' | head -1 || true)
if [ -z "$gh_ip" ]; then
    echo "ERROR: firewall verification FAILED — api.github.com does not resolve via dnsmasq" >&2
    exit 1
fi
if ! ipset test allowed-domains "$gh_ip" >/dev/null 2>&1; then
    echo "ERROR: firewall verification FAILED — dnsmasq resolved api.github.com to $gh_ip but did not add it to the ipset" >&2
    exit 1
fi
echo "  OK: api.github.com resolved to $gh_ip and is in the ipset"
if ! curl --connect-timeout 5 -s https://api.github.com/zen >/dev/null 2>&1; then
    echo "ERROR: firewall verification FAILED — api.github.com is NOT reachable" >&2
    exit 1
fi
echo "  OK: api.github.com is reachable as expected"
echo "Firewall configuration complete."
