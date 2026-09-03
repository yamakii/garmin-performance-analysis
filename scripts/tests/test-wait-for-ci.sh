#!/usr/bin/env bash
# Self-test for scripts/wait-for-ci.sh.
#
# Hermetic: `curl` is replaced by a PATH shim that serves canned GitHub API
# responses from a scenario directory, so no network and no token are needed
# (a dummy GITHUB_TOKEN is exported). The shim serves
#   .../pulls/<n>                 -> pull.json        (head.sha)
#   .../commits/<sha>/check-runs  -> check-runs.<k>.json, k = call counter
# so a scenario can move ci-guard from in_progress to completed across polls.
#
# Usage: bash scripts/tests/test-wait-for-ci.sh   (run from repo root)
# Exit 0 if all cases pass; prints failing expectations and exits 1 otherwise.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WAIT="$SCRIPT_DIR/wait-for-ci.sh"

failures=0
fail() { echo "  FAIL: $*" >&2; failures=$((failures + 1)); }

# make_scenario <dir> <sha> <state1> [<state2> ...]
# Each state is "status:conclusion" for ci-guard; "absent" = no ci-guard yet.
make_scenario() {
  local dir="$1" sha="$2"; shift 2
  mkdir -p "$dir"
  printf '{"number": 1, "head": {"sha": "%s"}}\n' "$sha" >"$dir/pull.json"
  local k=1 st
  for st in "$@"; do
    if [ "$st" = "absent" ]; then
      cat >"$dir/check-runs.$k.json" <<'EOF'
{"total_count": 1, "check_runs": [{"name": "web-frontend", "status": "completed", "conclusion": "skipped"}]}
EOF
    else
      local status="${st%%:*}" conclusion="${st#*:}"
      [ "$conclusion" = "$status" ] && conclusion=""
      printf '{"total_count": 2, "check_runs": [{"name": "web-frontend", "status": "completed", "conclusion": "skipped"}, {"name": "ci-guard", "status": "%s", "conclusion": %s}]}\n' \
        "$status" "$([ -n "$conclusion" ] && printf '"%s"' "$conclusion" || printf null)" >"$dir/check-runs.$k.json"
    fi
    k=$((k + 1))
  done
  echo 0 >"$dir/counter"
}

# Build the curl shim. It reads SCENARIO from the environment.
setup_shim() {
  local dir; dir="$(mktemp -d)"
  cat >"$dir/curl" <<'EOF'
#!/usr/bin/env bash
# Last argument is the URL.
url="${@: -1}"
case "$url" in
  */pulls/*) cat "$SCENARIO/pull.json" ;;
  */check-runs*)
    n=$(cat "$SCENARIO/counter"); n=$((n + 1)); echo "$n" >"$SCENARIO/counter"
    f="$SCENARIO/check-runs.$n.json"
    # Past the last scripted state, keep serving the last one.
    while [ ! -e "$f" ] && [ "$n" -gt 1 ]; do n=$((n - 1)); f="$SCENARIO/check-runs.$n.json"; done
    cat "$f" ;;
  *) echo '{"message": "shim: unexpected url '"$url"'"}' ;;
esac
EOF
  chmod +x "$dir/curl"
  echo "$dir"
}

SHIM="$(setup_shim)"
run_wait() {  # run_wait <scenario-dir> <args...>; sets OUT and RC
  local scenario="$1"; shift
  OUT="$(SCENARIO="$scenario" GITHUB_TOKEN="dummy" PATH="$SHIM:$PATH" bash "$WAIT" --repo o/r --interval 0 "$@" 2>/tmp/wait-for-ci-test.err)"
  RC=$?
  ERR="$(cat /tmp/wait-for-ci-test.err)"
}

test_success_exits_0() {
  echo "test_success_exits_0"
  local s; s="$(mktemp -d)"
  make_scenario "$s" abc123 "absent" "in_progress:" "completed:success"
  run_wait "$s" 1 --timeout 60
  [ "$RC" -eq 0 ] || fail "expected exit 0, got $RC (stderr: $ERR)"
  echo "$OUT" | grep -q '"conclusion":"success"' || fail "expected conclusion success in: $OUT"
  echo "$OUT" | grep -q '"sha":"abc123"' || fail "expected sha in: $OUT"
  [ "$(cat "$s/counter")" -eq 3 ] || fail "expected 3 check-runs polls, got $(cat "$s/counter")"
}

test_failure_exits_1() {
  echo "test_failure_exits_1"
  local s; s="$(mktemp -d)"
  make_scenario "$s" def456 "completed:failure"
  run_wait "$s" 2 --timeout 60
  [ "$RC" -eq 1 ] || fail "expected exit 1, got $RC"
  echo "$OUT" | grep -q '"conclusion":"failure"' || fail "expected conclusion failure in: $OUT"
}

test_timeout_exits_2() {
  echo "test_timeout_exits_2"
  local s; s="$(mktemp -d)"
  make_scenario "$s" 0a0a0a "in_progress:"
  run_wait "$s" 3 --timeout 1 --interval 1
  [ "$RC" -eq 2 ] || fail "expected exit 2, got $RC"
  echo "$OUT" | grep -q '"conclusion":"timeout"' || fail "expected timeout marker in: $OUT"
  echo "$OUT" | grep -q '"status":"in_progress"' || fail "expected last status in: $OUT"
}

test_missing_token_exits_3() {
  echo "test_missing_token_exits_3"
  local out rc
  out="$(GITHUB_TOKEN="" PATH="$SHIM:$PATH" bash "$WAIT" --repo o/r 4 2>&1)"; rc=$?
  [ "$rc" -eq 3 ] || fail "expected exit 3, got $rc"
  echo "$out" | grep -q "GITHUB_TOKEN" || fail "expected GITHUB_TOKEN message, got: $out"
}

test_bad_pr_exits_3() {
  echo "test_bad_pr_exits_3"
  local rc
  GITHUB_TOKEN="dummy" bash "$WAIT" --repo o/r notanumber >/dev/null 2>&1; rc=$?
  [ "$rc" -eq 3 ] || fail "expected exit 3 for non-numeric PR, got $rc"
}

test_api_error_exits_3() {
  echo "test_api_error_exits_3"
  local s; s="$(mktemp -d)"
  mkdir -p "$s"; echo '{"message": "Bad credentials"}' >"$s/pull.json"; echo 0 >"$s/counter"
  run_wait "$s" 5 --timeout 5
  [ "$RC" -eq 3 ] || fail "expected exit 3 on API error, got $RC"
  echo "$ERR" | grep -q "Bad credentials" || fail "expected API message on stderr, got: $ERR"
}

test_success_exits_0
test_failure_exits_1
test_timeout_exits_2
test_missing_token_exits_3
test_bad_pr_exits_3
test_api_error_exits_3

if [ "$failures" -ne 0 ]; then
  echo "test-wait-for-ci: $failures failure(s)" >&2
  exit 1
fi
echo "test-wait-for-ci: all cases pass"
