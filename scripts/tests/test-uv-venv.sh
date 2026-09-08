#!/usr/bin/env bash
# Self-test for docker/lib/uv-venv.sh and docker/uv-wrapper.sh (#1047).
# Hermetic: temp git repos, a fake real `uv` that prints the variable, no docker.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../../docker/lib/uv-venv.sh
. "$ROOT/docker/lib/uv-venv.sh"

failures=0
ok() { echo "  ok: $1"; }
fail() { echo "  FAIL: $*" >&2; failures=$((failures + 1)); }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
export UV_VENV_BASE="$tmp/venvs"

mkrepo() { # path
  mkdir -p "$1/packages/garmin-mcp-server" "$1/packages/garmin-web/frontend"
  git -C "$1" init -q
}
mkrepo "$tmp/repoA"
mkrepo "$tmp/repoB"
mkdir -p "$tmp/nogit"

# --- test_uv_venv_path_server_vs_web -----------------------------------------
web="$(uv_venv_path "$tmp/repoA/packages/garmin-web/frontend")"
server="$(uv_venv_path "$tmp/repoA/packages/garmin-mcp-server")"
rootv="$(uv_venv_path "$tmp/repoA")"
if [[ "$web" == "$tmp/venvs/"*-web ]] && [[ "$server" == "$tmp/venvs/"*-server ]] && [ "$rootv" = "$server" ]; then
  ok test_uv_venv_path_server_vs_web
else
  fail "test_uv_venv_path_server_vs_web: web='$web' server='$server' root='$rootv'"
fi

# --- test_uv_venv_path_two_worktrees_differ ----------------------------------
a="$(uv_venv_path "$tmp/repoA")"
b="$(uv_venv_path "$tmp/repoB")"
a2="$(cd "$tmp/repoA/packages" && uv_venv_path .)"
if [ "$a" != "$b" ] && [ "$a" = "$a2" ]; then
  ok test_uv_venv_path_two_worktrees_differ
else
  fail "test_uv_venv_path_two_worktrees_differ: a='$a' b='$b' a2='$a2'"
fi

# --- test_uv_venv_path_outside_git_fails -------------------------------------
out="$(uv_venv_path "$tmp/nogit")"; rc=$?
if [ "$rc" -eq 1 ] && [ -z "$out" ]; then
  ok test_uv_venv_path_outside_git_fails
else
  fail "test_uv_venv_path_outside_git_fails: rc=$rc out='$out'"
fi

# --- test_uv_project_dir_flags -----------------------------------------------
d1="$(uv_project_dir run --directory "$tmp/repoB" pytest)"
d2="$(uv_project_dir run "--project=$tmp/repoB" pytest)"
d3="$(cd "$tmp/repoA" && uv_project_dir run pytest)"
if [ "$d1" = "$tmp/repoB" ] && [ "$d2" = "$tmp/repoB" ] && [ "$d3" = "$tmp/repoA" ]; then
  ok test_uv_project_dir_flags
else
  fail "test_uv_project_dir_flags: d1='$d1' d2='$d2' d3='$d3'"
fi

# --- wrapper tests: a fake real uv prints the variable it received -----------
fake="$tmp/fake-uv"
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "${UV_PROJECT_ENVIRONMENT-<unset>}"\n' >"$fake"
chmod +x "$fake"
wrapper="$ROOT/docker/uv-wrapper.sh"
export UV_REAL="$fake" UV_VENV_LIB="$ROOT/docker/lib/uv-venv.sh"

# --- test_wrapper_exports_from_directory_flag --------------------------------
got="$(cd "$tmp/repoA" && env -u UV_PROJECT_ENVIRONMENT bash "$wrapper" run --directory "$tmp/repoB/packages/garmin-web" pytest)"
if [ "$got" = "$(uv_venv_path "$tmp/repoB/packages/garmin-web")" ]; then
  ok test_wrapper_exports_from_directory_flag
else
  fail "test_wrapper_exports_from_directory_flag: got '$got'"
fi

# --- test_wrapper_honours_explicit_env ---------------------------------------
got="$(cd "$tmp/repoA" && UV_PROJECT_ENVIRONMENT=/x bash "$wrapper" run pytest)"
if [ "$got" = "/x" ]; then
  ok test_wrapper_honours_explicit_env
else
  fail "test_wrapper_honours_explicit_env: got '$got'"
fi

# --- test_wrapper_passthrough_outside_git ------------------------------------
got="$(cd "$tmp/nogit" && env -u UV_PROJECT_ENVIRONMENT bash "$wrapper" --version)"
if [ "$got" = "<unset>" ]; then
  ok test_wrapper_passthrough_outside_git
else
  fail "test_wrapper_passthrough_outside_git: got '$got'"
fi

if [ "$failures" -ne 0 ]; then
  echo "test-uv-venv: $failures failure(s)" >&2
  exit 1
fi
echo "All uv-venv tests passed"
