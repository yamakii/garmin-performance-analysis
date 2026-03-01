# Worktree Commands

## `cd <path> && ...` を使わない

worktree 内でコマンドを実行する際、`cd <path> && <cmd>` は compound コマンドとして Claude Code が毎回承認を求める。各ツールのディレクトリ指定オプションを使う。

### git 操作 — `git -C <path>`

| 用途 | コマンド |
|------|---------|
| ステージ | `git -C <path> add file1 file2` |
| コミット | `git -C <path> commit -m "msg"` |
| 状態確認 | `git -C <path> status` |
| 差分 | `git -C <path> diff` |
| ログ | `git -C <path> log --oneline -5` |
| プッシュ | `git -C <path> push -u origin branch` |
| ブランチ作成 | `git -C <path> checkout -b branch` |
| stash | `git -C <path> stash` |
| fetch | `git -C <path> fetch origin` |

### uv / pytest / ruff / pre-commit — `--directory`

| 用途 | コマンド |
|------|---------|
| テスト | `uv run --directory <path> pytest -m unit -v` |
| lint | `uv run --directory <path> ruff check src/` |
| pre-commit | `uv run --directory <path> pre-commit run --all-files` |
