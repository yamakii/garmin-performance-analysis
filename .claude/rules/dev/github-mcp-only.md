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

### CI チェック完了の確認

`pull_request_read(method="get_check_runs", pullNumber=N)` が head commit の check-runs を返す。
- required check は **`ci-guard`** — `conclusion: "success"` ならマージ可。
- `web-backend` / `web-frontend` は `packages/garmin-web/**` 変更時のみ走り、それ以外は `conclusion: "skipped"`（正常）。
- 旧 `get_pull_request_status` は commit statuses API（GitHub Actions の check-runs は見えず常に空）だったため使わない。

### 引数の注意

- PR 系ツールの引数は **`pullNumber`**（旧 `pull_number` から変更）。issue 系は従来どおり `issue_number`。
- `issue_read` / `issue_write` / `pull_request_read` は `method` 必須。

## リポジトリ情報

全 MCP ツール呼び出しで使用:
- `owner`: `"yamakii"`
- `repo`: `"garmin-performance-analysis"`

## ブランチ削除

`merge_pull_request` に `--delete-branch` 相当はない。GitHub リポジトリ設定で auto-delete が有効なため不要。
