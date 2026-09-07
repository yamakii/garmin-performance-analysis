#!/bin/bash
# WebFetch allowlist pre-check for the sandbox container (#1035).
#
# WebSearch runs server-side and sees the whole web; WebFetch runs inside the
# container and is gated by docker/allowed-domains.txt (dnsmasq refuses every
# other name). A blocked host surfaces as a bare "Command failed with no output",
# indistinguishable from a transient error, so the model retries and the owner
# never learns that one allowlist line would fix it.
#
# This hook checks the URL host against the SAME allowlist the running container
# was built with (the image-baked copy that dnsmasq reads), using dnsmasq's
# semantics — an entry covers the domain and every subdomain — and blocks an
# unlisted host with a message that says what to do. No DNS lookup: deterministic.
#
# Outside the container (no image-baked allowlist) it does nothing.
set -euo pipefail

ALLOWLIST="${SANDBOX_ALLOWLIST:-/etc/sandbox/allowed-domains.txt}"
[ -r "$ALLOWLIST" ] || exit 0

input=$(cat)
host=$(echo "$input" | python3 -c "
import sys, json
from urllib.parse import urlsplit
try:
    url = json.load(sys.stdin).get('tool_input', {}).get('url', '')
    print((urlsplit(url).hostname or '').lower())
except Exception:
    print('')
" 2>/dev/null) || exit 0
[ -n "$host" ] || exit 0

while IFS= read -r raw || [ -n "$raw" ]; do
  entry="${raw%%#*}"
  entry="${entry//[[:space:]]/}"
  [ -n "$entry" ] || continue
  entry="${entry,,}"
  if [ "$host" = "$entry" ] || [[ "$host" == *".$entry" ]]; then
    exit 0
  fi
done <"$ALLOWLIST"

cat >&2 <<EOF
BLOCKED: WebFetch — '$host' はこの sandbox の egress allowlist に無いため取得できません。
  コンテナ内の dnsmasq が名前解決を拒否するため、実行しても無言の "Command failed with no output" になります。
  必要なら: docker/allowed-domains.txt に '$host'（またはその親ドメイン）を 1 行追加 → docker/run.sh で再ビルド。
  代替: WebSearch の要約・スニペットで足りるならそちらを使う。同じホストへの再試行は無意味です。
EOF
exit 2
