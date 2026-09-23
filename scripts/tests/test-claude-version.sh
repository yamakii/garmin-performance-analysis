#!/usr/bin/env bash
# Self-test for docker/lib/claude-version.sh (#1346).
#
# Hermetic: a temp dir holds PATH shims for `npm` and `curl` that record their
# calls and print canned answers, so nothing reaches the network and no docker
# build runs. Guards the property the bug was about — a plain rebuild must pass a
# CONCRETE version as the build-arg, because the literal `latest` keeps hitting
# the cached `npm install -g` layer.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../../docker/lib/claude-version.sh
. "$ROOT/docker/lib/claude-version.sh"

failures=0
ok() { echo "  ok: $1"; }
fail() { echo "  FAIL: $*" >&2; failures=$((failures + 1)); }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
bin="$tmp/bin"
mkdir -p "$bin"
# Keep only the shims plus coreutils (grep/sed/head/tr live in /usr/bin:/bin).
export PATH="$bin:/usr/bin:/bin"

calls="$tmp/calls"

# shim <name> <exit> [stdout]
shim() {
  cat >"$bin/$1" <<SHIM
#!/usr/bin/env bash
echo "$1 \$*" >>"$calls"
[ -n "${3:-}" ] && printf '%s\n' '${3:-}'
exit $2
SHIM
  chmod +x "$bin/$1"
}

reset_calls() { : >"$calls"; }

REGISTRY_DOC='{"name":"@anthropic-ai/claude-code","_nodeVersion":"24.4.0","_npmVersion":"11.19.0","version":"2.1.279","dist":{"tarball":"https://registry.npmjs.org/x.tgz"}}'

# --- test_resolve_explicit_pin_passthrough ------------------------------------
# A pin must not be rewritten, and must not cost a registry round trip.
shim npm 0 "2.1.280"
shim curl 0 "$REGISTRY_DOC"
reset_calls
got="$(claude_version_resolve "2.1.193")"
if [ "$got" = "2.1.193" ] && [ ! -s "$calls" ]; then
  ok test_resolve_explicit_pin_passthrough
else
  fail "test_resolve_explicit_pin_passthrough: got='$got' calls='$(cat "$calls")'"
fi

# --- test_resolve_latest_prefers_npm -----------------------------------------
reset_calls
got="$(claude_version_resolve "latest")"
if [ "$got" = "2.1.280" ] && grep -q '^npm view' "$calls" && ! grep -q '^curl' "$calls"; then
  ok test_resolve_latest_prefers_npm
else
  fail "test_resolve_latest_prefers_npm: got='$got' calls='$(cat "$calls")'"
fi

# --- test_resolve_empty_request_is_latest ------------------------------------
got="$(claude_version_resolve)"
if [ "$got" = "2.1.280" ]; then
  ok test_resolve_empty_request_is_latest
else
  fail "test_resolve_empty_request_is_latest: got='$got'"
fi

# --- test_resolve_latest_falls_back_to_curl ----------------------------------
shim npm 1 ""
reset_calls
got="$(claude_version_resolve "latest")"
if [ "$got" = "2.1.279" ] && grep -q '^curl' "$calls"; then
  ok test_resolve_latest_falls_back_to_curl
else
  fail "test_resolve_latest_falls_back_to_curl: got='$got' calls='$(cat "$calls")'"
fi

# --- test_parse_picks_version_not_npm_metadata -------------------------------
got="$(claude_version_parse "$REGISTRY_DOC")"
spaced="$(claude_version_parse '{"name":"x", "version" : "3.0.1-beta.2" }')"
empty="$(claude_version_parse '{"name":"x"}')"
if [ "$got" = "2.1.279" ] && [ "$spaced" = "3.0.1-beta.2" ] && [ -z "$empty" ]; then
  ok test_parse_picks_version_not_npm_metadata
else
  fail "test_parse_picks_version_not_npm_metadata: got='$got' spaced='$spaced' empty='$empty'"
fi

# --- test_resolve_rejects_non_semver -----------------------------------------
# Registry error text must never reach the build-arg.
shim npm 0 "npm ERR! network request failed"
shim curl 1 ""
got="$(claude_version_resolve "latest")"; rc=$?
if [ "$got" = "latest" ] && [ "$rc" -ne 0 ]; then
  ok test_resolve_rejects_non_semver
else
  fail "test_resolve_rejects_non_semver: got='$got' rc=$rc"
fi

# --- test_resolve_unreachable_falls_back_to_latest ---------------------------
rm -f "$bin/npm" "$bin/curl"
export PATH="$bin"          # no npm, no curl at all
got="$(claude_version_resolve "latest")"; rc=$?
pinned="$(claude_version_resolve "2.1.193")"; prc=$?
export PATH="$bin:/usr/bin:/bin"
if [ "$got" = "latest" ] && [ "$rc" -ne 0 ] && [ "$pinned" = "2.1.193" ] && [ "$prc" -eq 0 ]; then
  ok test_resolve_unreachable_falls_back_to_latest
else
  fail "test_resolve_unreachable_falls_back_to_latest: got='$got' rc=$rc pinned='$pinned' prc=$prc"
fi

if [ "$failures" -ne 0 ]; then
  echo "test-claude-version: $failures failure(s)" >&2
  exit 1
fi
echo "All claude-version tests passed"
