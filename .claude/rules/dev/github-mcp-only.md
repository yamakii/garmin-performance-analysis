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
- **完了待ちは `bash scripts/wait-for-ci.sh <PR>` を使う**（唯一の非 MCP 例外）。read-only の REST 取得を `GITHUB_TOKEN` で行い、
  `ci-guard` が completed になるまで 1 コマンドでブロックする（`sleep` → `get_check_runs` の LLM ループ禁止、dev-reference §8）。
  書き込み（merge / comment / issue）は引き続き MCP のみ。exit 3（token 無し等）のときだけ `get_check_runs` で手動ポーリングする。

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
    "X-MCP-Toolsets": "default,actions"
  }
}
```

`default,actions` は既定 44 tool を1つも失わずに 4 tool を足す（`all` は 93 tool でコンテキスト肥大のため不採用）。
**反映にはセッション再接続が必要**（既存セッションは `/mcp`、または新規セッション起動）。

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
