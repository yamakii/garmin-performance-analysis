#!/usr/bin/env bash
# Self-test for docker/lib/gen-managed-settings.sh — the managed-settings policy
# the sandbox container writes for Claude Code's built-in Bash sandbox (#1028).
#
# Runs without root, docker or network: it sources the generator and asserts the
# JSON it prints with jq. The runtime (bubblewrap present, file written at boot)
# is exercised by the CI docker-build smoke (docker/sandbox-smoke.sh).
#
# Usage: bash scripts/tests/test-sandbox-managed-settings.sh   (run from repo root)
# Exit 0 if all cases pass; prints the failing expectation and exits 1 otherwise.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GEN="$ROOT/docker/lib/gen-managed-settings.sh"
# shellcheck source=../../docker/lib/gen-managed-settings.sh
. "$GEN"

failures=0
fail() {
  echo "  FAIL: $*" >&2
  failures=$((failures + 1))
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
printf 'pypi.org\n' >"$tmp/one.txt"

# Isolate every case from the caller's environment.
run_gen() {
  env -i PATH="$PATH" HOME="$HOME" "$@" bash -c ". '$GEN'; gen_managed_settings '$tmp/one.txt'"
}

# --- test_managed_settings_allowed_domains_from_allowlist --------------------
out="$(run_gen)"
if [ "$(jq -c '.sandbox.network.allowedDomains' <<<"$out")" = '["pypi.org","*.pypi.org"]' ]; then
  echo "  ok: test_managed_settings_allowed_domains_from_allowlist"
else
  fail "test_managed_settings_allowed_domains_from_allowlist: $(jq -c '.sandbox.network.allowedDomains' <<<"$out")"
fi
if [ "$(jq -r '.sandbox.enabled, .sandbox.enableWeakerNestedSandbox, .sandbox.autoAllowBashIfSandboxed' <<<"$out" | tr '\n' ' ')" = "true true true " ]; then
  echo "  ok: test_managed_settings_allowed_domains_from_allowlist (booleans)"
else
  fail "test_managed_settings_allowed_domains_from_allowlist: sandbox booleans"
fi

# --- test_managed_settings_allow_write_includes_env_dirs ---------------------
with_dir="$(run_gen GARMIN_DATA_DIR=/data/x)"
if jq -e '.sandbox.filesystem.allowWrite | index("/data/x") and index("/home/claude/uv-venv")' <<<"$with_dir" >/dev/null; then
  echo "  ok: test_managed_settings_allow_write_includes_env_dirs"
else
  fail "test_managed_settings_allow_write_includes_env_dirs: $(jq -c '.sandbox.filesystem.allowWrite' <<<"$with_dir")"
fi
if jq -e '.sandbox.filesystem.allowWrite | index("/data/x") | not' <<<"$out" >/dev/null; then
  echo "  ok: test_managed_settings_allow_write_includes_env_dirs (unset var adds nothing)"
else
  fail "test_managed_settings_allow_write_includes_env_dirs: /data/x present without the var"
fi

# --- test_managed_settings_mask_opt_in ---------------------------------------
masked="$(run_gen CLAUDE_CREDENTIAL_MASK=1)"
if [ "$(jq -c '.sandbox.network.tlsTerminate' <<<"$masked")" = '{}' ]; then
  echo "  ok: test_managed_settings_mask_opt_in (tlsTerminate)"
else
  fail "test_managed_settings_mask_opt_in: tlsTerminate missing"
fi
names="$(jq -r '.sandbox.credentials.envVars[].name' <<<"$masked" | sort | tr '\n' ' ')"
if [ "$names" = "GARMIN_PASSWORD GITHUB_TOKEN " ]; then
  echo "  ok: test_managed_settings_mask_opt_in (both secrets masked)"
else
  fail "test_managed_settings_mask_opt_in: envVars names '$names'"
fi
if jq -e '
    .sandbox.credentials.envVars[]
    | select(.name == "GARMIN_PASSWORD")
    | .mode == "mask" and (.injectHosts - ["sso.garmin.com","diauth.garmin.com","connect.garmin.com","connectapi.garmin.com"] | length == 0)
  ' <<<"$masked" >/dev/null; then
  echo "  ok: test_managed_settings_mask_opt_in (GARMIN_PASSWORD injectHosts ⊆ garmin hosts)"
else
  fail "test_managed_settings_mask_opt_in: GARMIN_PASSWORD injectHosts"
fi
if jq -e '(.sandbox | has("credentials") | not) and (.sandbox.network | has("tlsTerminate") | not)' <<<"$out" >/dev/null; then
  echo "  ok: test_managed_settings_mask_opt_in (default: no mask, no tlsTerminate)"
else
  fail "test_managed_settings_mask_opt_in: default output carries credentials/tlsTerminate"
fi

# --- test_managed_settings_disabled ------------------------------------------
off="$(run_gen CLAUDE_SANDBOX=0)"
if [ "$(jq -c . <<<"$off")" = '{"sandbox":{"enabled":false}}' ]; then
  echo "  ok: test_managed_settings_disabled"
else
  fail "test_managed_settings_disabled: got '$off'"
fi

# --- test_managed_settings_disabled_when_userns_unavailable -------------------
# entrypoint.sh sets SANDBOX_USERNS_OK=0 when bubblewrap cannot create a user
# namespace; the policy must then be an explicit off (bwrap present but failing
# breaks every sandboxed Bash command instead of falling back).
no_userns="$(run_gen SANDBOX_USERNS_OK=0)"
if [ "$(jq -c . <<<"$no_userns")" = '{"sandbox":{"enabled":false}}' ]; then
  echo "  ok: test_managed_settings_disabled_when_userns_unavailable"
else
  fail "test_managed_settings_disabled_when_userns_unavailable: got '$no_userns'"
fi
if jq -e '.sandbox.enabled == true' <<<"$(run_gen SANDBOX_USERNS_OK=1)" >/dev/null; then
  echo "  ok: test_managed_settings_disabled_when_userns_unavailable (probe ok → enabled)"
else
  fail "test_managed_settings_disabled_when_userns_unavailable: SANDBOX_USERNS_OK=1 did not enable"
fi

# --- test_managed_settings_executed_writes_file ------------------------------
if bash "$GEN" "$tmp/one.txt" "$tmp/out/managed-settings.json" \
   && jq -e '.sandbox.enabled == true' "$tmp/out/managed-settings.json" >/dev/null \
   && [ ! -e "$tmp/out/managed-settings.json.tmp" ]; then
  echo "  ok: test_managed_settings_executed_writes_file"
else
  fail "test_managed_settings_executed_writes_file"
fi

# --- test_managed_settings_rejects_invalid_allowlist -------------------------
printf 'bad host!\n' >"$tmp/bad.txt"
if bash "$GEN" "$tmp/bad.txt" "$tmp/out/bad.json" 2>/dev/null; then
  fail "test_managed_settings_rejects_invalid_allowlist: produced output from an invalid list"
else
  echo "  ok: test_managed_settings_rejects_invalid_allowlist"
fi

if [ "$failures" -eq 0 ]; then
  echo "All sandbox-managed-settings tests passed"
  exit 0
fi
echo "$failures sandbox-managed-settings test(s) failed" >&2
exit 1
