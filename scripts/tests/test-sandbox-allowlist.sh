#!/usr/bin/env bash
# Self-test for docker/lib/allowlist.sh — the pure logic behind the sandbox
# egress gate (docker/allowed-domains.txt → dnsmasq config → ipset feed).
#
# Runs without root, network or docker: it only sources the helper library and
# checks its stdout. The runtime (dnsmasq + iptables) is exercised by the CI
# docker-build smoke (docker/sandbox-smoke.sh).
#
# Usage: bash scripts/tests/test-sandbox-allowlist.sh   (run from repo root)
# Exit 0 if all cases pass; prints the failing expectation and exits 1 otherwise.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../../docker/lib/allowlist.sh
. "$ROOT/docker/lib/allowlist.sh"

failures=0
fail() {
  echo "  FAIL: $*" >&2
  failures=$((failures + 1))
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# --- test_allowlist_strips_comments_and_blank_lines ---------------------------
printf '# leading comment\n\n  PyPI.org  \nfiles.pythonhosted.org # trailing comment\n' >"$tmp/basic.txt"
out="$(allowlist_domains "$tmp/basic.txt")"
expected=$'pypi.org\nfiles.pythonhosted.org'
if [ "$out" = "$expected" ]; then
  echo "  ok: test_allowlist_strips_comments_and_blank_lines"
else
  fail "test_allowlist_strips_comments_and_blank_lines: got '$out'"
fi

# --- test_allowlist_rejects_invalid_entry ------------------------------------
printf 'good.example\nbad host!\nnever.reached\n' >"$tmp/invalid.txt"
err="$(allowlist_domains "$tmp/invalid.txt" 2>&1 >/dev/null)"
rc=$?
if [ "$rc" -eq 1 ] && [[ "$err" == *"invalid.txt:2"* ]] && [[ "$err" == *"bad host!"* ]]; then
  echo "  ok: test_allowlist_rejects_invalid_entry"
else
  fail "test_allowlist_rejects_invalid_entry: rc=$rc stderr='$err'"
fi

# --- test_dnsmasq_conf_emits_server_and_ipset_per_domain ---------------------
printf 'a.example\nb.example\n' >"$tmp/two.txt"
conf="$(dnsmasq_conf "$tmp/two.txt" 10.0.0.1 10.0.0.2)"
for line in \
  'no-resolv' \
  'listen-address=127.0.0.1' \
  'server=/a.example/10.0.0.1' \
  'server=/a.example/10.0.0.2' \
  'server=/b.example/10.0.0.1' \
  'ipset=/a.example/allowed-domains' \
  'ipset=/b.example/allowed-domains'; do
  if ! grep -qxF "$line" <<<"$conf"; then
    fail "test_dnsmasq_conf_emits_server_and_ipset_per_domain: missing '$line'"
  fi
done
echo "  ok: test_dnsmasq_conf_emits_server_and_ipset_per_domain (checked)"

# --- test_dnsmasq_conf_has_no_default_upstream --------------------------------
# A bare `server=<ip>` would forward EVERY name upstream, defeating the gate.
if grep -qE '^server=[^/]' <<<"$conf"; then
  fail "test_dnsmasq_conf_has_no_default_upstream: found a bare server= line"
else
  echo "  ok: test_dnsmasq_conf_has_no_default_upstream"
fi
if dnsmasq_conf "$tmp/two.txt" >/dev/null 2>&1; then
  fail "test_dnsmasq_conf_has_no_default_upstream: accepted a call with no upstream"
else
  echo "  ok: test_dnsmasq_conf_has_no_default_upstream (no upstream → error)"
fi

# --- test_dnsmasq_conf_propagates_invalid_allowlist --------------------------
if dnsmasq_conf "$tmp/invalid.txt" 10.0.0.1 >/dev/null 2>&1; then
  fail "test_dnsmasq_conf_propagates_invalid_allowlist: produced config from an invalid list"
else
  echo "  ok: test_dnsmasq_conf_propagates_invalid_allowlist"
fi

# --- test_shipped_allowlist_is_valid -----------------------------------------
# The real file must parse, or the container will refuse to start (fail-closed).
if n="$(allowlist_domains "$ROOT/docker/allowed-domains.txt" | wc -l)" && [ "$n" -gt 10 ]; then
  echo "  ok: test_shipped_allowlist_is_valid ($n domains)"
else
  fail "test_shipped_allowlist_is_valid"
fi

if [ "$failures" -eq 0 ]; then
  echo "All sandbox-allowlist tests passed"
  exit 0
fi
echo "$failures sandbox-allowlist test(s) failed" >&2
exit 1
