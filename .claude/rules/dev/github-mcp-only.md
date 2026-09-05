# GitHub MCP Only

## GitHub 操作は `mcp__github__*` ツールを使用すること

`gh` CLI は deny 設定でブロック済み。全 GitHub 操作は MCP ツール経由で行う。

> 公式 `github/github-mcp-server`（#330 で移行）。issue/PR の read/write は **method ベースの統合ツール**になっている点に注意。

## コマンド対応表

| gh CLI | MCP ツール |
|--------|-----------|
| `gh issue view N` | `mcp__github__issue_read(method="get", owner, repo, issue_number)` |
| `gh issue create` | `mcp__github__issue_write(method="create", owner, repo, title, body, labels)` |
| `gh issue edit N` | `mcp__github__issue_write(method="update", owner, repo, issue_number, ...)` |
| `gh issue close N` | `mcp__github__issue_write(method="update", owner, repo, issue_number, state="closed")` |
| `gh issue list` | `mcp__github__list_issues(owner, repo, state, labels)` — state は `OPEN`/`CLOSED`（大文字）、direction は `ASC`/`DESC` |
| `gh issue comment N` | `mcp__github__add_issue_comment(owner, repo, issue_number, body)` |
| `gh pr view N` | `mcp__github__pull_request_read(method="get", owner, repo, pullNumber)` |
| `gh pr create` | `mcp__github__create_pull_request(owner, repo, title, head, base, body)` |
| `gh pr list` | `mcp__github__list_pull_requests(owner, repo, state, head)` — state は `open`/`closed`/`all`（小文字） |
| `gh pr merge N` | `mcp__github__merge_pull_request(owner, repo, pullNumber, merge_method)` |
| `gh pr checks N` | `mcp__github__pull_request_read(method="get_check_runs", owner, repo, pullNumber)` |
| `gh run view --log-failed` | `mcp__github__get_job_logs(owner, repo, run_id, failed_only=True, return_content=True)` — 要 `actions` toolset（後述） |

### CI チェック完了の確認

`pull_request_read(method="get_check_runs", pullNumber=N)` が head commit の check-runs を返す。
- required check は **`ci-guard`** — `conclusion: "success"` ならマージ可。
- `web-backend` / `web-frontend` は `packages/garmin-web/**` 変更時のみ走り、それ以外は `conclusion: "skipped"`（正常）。
- 旧 `get_pull_request_status` は commit statuses API（GitHub Actions の check-runs は見えず常に空）だったため使わない。
- **完了待ちは `bash scripts/wait-for-ci.sh <PR>` を使う**（非 MCP の例外）。read-only の REST 取得を `GITHUB_TOKEN` で行い、
  `ci-guard` が completed になるまで 1 コマンドでブロックする（`sleep` → `get_check_runs` の LLM ループ禁止、dev-reference §8）。
  書き込み（merge / comment / issue）は引き続き MCP のみ。exit 3（token 無し等）のときだけ `get_check_runs` で手動ポーリングする。
  **例外の理由は「MCP では check-runs が取れない」ではない**（`pull_request_read(get_check_runs)` で普通に取れる）。
  MCP に**ブロッキング待機がない**ため、LLM から `sleep` → 再取得を回すと 1 PR あたり 3-6 往復かかる、という
  往復コストの話であり、shell script は MCP を呼べないので REST になる。能力の欠如と読み替えないこと。
- **サブエージェント / Workflow 内ではフォアグラウンドで 1 回実行する**（Bash tool の timeout を 960000 ms 以上に）。
  `run_in_background` にして `Monitor` や `pgrep` / `kill -0` で終了を見張る書き方は、`Bash(kill:*)` の ask ルールに
  当たって権限プロンプトで止まり自律実行が壊れる（#993）。メインセッションが自分で待つときだけ `run_in_background` 可。

### CI ログの参照（失敗原因の調査）

`get_check_runs` は conclusion しか返さない。**失敗ログの本文は `mcp__github__get_job_logs`** で取る。

```
mcp__github__get_job_logs(
  owner="yamakii", repo="garmin-performance-analysis",
  run_id=<workflow run id>,   # or job_id=<単一 job>
  failed_only=True,           # run 内の失敗 job だけ
  return_content=True,        # URL ではなくログ本文を返す
  tail_lines=100,             # 末尾行数。まず 100 で足りる
)
```

run id は `mcp__github__actions_list` / `actions_get`、または `pull_request_read(method="get_check_runs")` の
check-run から辿る。

**この toolset は既定で無効**。ローカルの `.mcp.json`（git 管理外・ユーザーごと）に
`X-MCP-Toolsets` ヘッダを足して有効化する:

```jsonc
"github": {
  "type": "http",
  "url": "https://api.githubcopilot.com/mcp/",
  "headers": {
    "Authorization": "Bearer ${GITHUB_TOKEN}",
    "X-MCP-Toolsets": "default,actions,code_security,dependabot,secret_protection"
  }
}
```

既定 44 tool を1つも失わずに必要な toolset だけを足す（`all` は 93 tool でコンテキスト肥大のため不採用）。
**反映にはセッション再接続が必要**（既存セッションは `/mcp`、または新規セッション起動）。

### toolset 一覧（有効化しないとツールが「存在しない」）

| toolset | 主なツール | 用途 |
|---------|-----------|------|
| `default` | issue / PR / repo / user 系 44 tool | 既定 |
| `actions` | `actions_list`, `actions_get`, `get_job_logs`, `actions_run_trigger` | CI 実行とログ本文 |
| `code_security` | `list_code_scanning_alerts`, `get_code_scanning_alert` | CodeQL / code scanning alert |
| `dependabot` | `list_dependabot_alerts`, `get_dependabot_alert` | 依存の脆弱性 alert |
| `secret_protection` | `list_secret_scanning_alerts`, `get_secret_scanning_alert` | secret scanning alert |

> `code_security` 系は `security_events` スコープを持つ `GITHUB_TOKEN` が要る。403 が返るときは
> toolset ではなくトークンのスコープを疑う。

### 「MCP ではできない」と判断する前に toolset を疑う

**ツールが見つからない ≠ MCP で不可能。** 既定では 44 tool しか露出しておらず、未有効の toolset の
ツールは名前ごと存在しないように見える。これを能力の欠如と誤読して `curl` / `gh` の回避策を
書くのが定番の失敗で、実際に 2 回起きている:

1. **GHA ログ**（#330 以降）: 「sandbox の egress で blob が取れない」は事実だが、`actions` を
   有効化すればサーバ側がログ本文を返して構造的に解決する。
2. **code scanning alert**（2026-09-05）: `X-MCP-Toolsets` が `default,actions` だったため
   `list_code_scanning_alerts` が生えておらず、REST への fallback を書きかけた。`code_security` を
   足して解決（#996）。

手順: ツールが無い → 上表と上流 README（`github/github-mcp-server`）で toolset を確認 →
`.mcp.json` に追記 → `/mcp` 再接続。**それでも無い場合に限り**非 MCP 経路を検討する。

`actions_run_trigger`（re-run / cancel）は write tool。`workflow-orchestration.md` の Autonomy Boundaries に
従い実行前に確認する。read-only に固定したいなら `settings.local.json` の deny に
`mcp__github__actions_run_trigger` を足す（`X-MCP-Readonly` はサーバ全体に効き `merge_pull_request` を
壊すため使わない）。

### sandbox から `gh` / `curl` でログを取れない理由

`GET /repos/{o}/{r}/actions/jobs/{id}/logs` は **302 で Azure Blob**
（`productionresultssa*.blob.core.windows.net`）にリダイレクトする。sandbox の egress allowlist は
GitHub API ホストのみで、blob ホストは DNS は引けても TCP 443 が `No route to host` になる。

- run / job の **metadata は取れるがログ本文だけ取れない**
- `gh` は sandbox に未インストールで、入れても同じ blob を取りに行くため解決しない（deny `Bash(gh:*)` を緩める意味は無い）
- hosted MCP サーバは**ログ取得をサーバ側で実行**して本文を MCP 接続経由で返すため、この制限を構造的に回避できる

### 引数の注意

- PR 系ツールの引数は **`pullNumber`**（旧 `pull_number` から変更）。issue 系は従来どおり `issue_number`。
- `issue_read` / `issue_write` / `pull_request_read` は `method` 必須。

## リポジトリ情報

全 MCP ツール呼び出しで使用:
- `owner`: `"yamakii"`
- `repo`: `"garmin-performance-analysis"`

## ブランチ削除

`merge_pull_request` に `--delete-branch` 相当はない。GitHub リポジトリ設定で auto-delete が有効なため不要。
