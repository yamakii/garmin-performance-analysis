#!/bin/bash
# SessionStart: リポジトリの git 設定で merge / pull の diffstat を止める（#1307）。
# `--no-stat` の付け忘れや、セッション開始時に固定された旧ルールで動くセッションでも
# 取り込んだ全ファイルの diffstat がコンテキストに流れないようにする（git.md §1）。
# .git/config は全 worktree で共有される。冪等で、失敗してもセッションは止めない。

dir="${CLAUDE_PROJECT_DIR:-.}"
git -C "$dir" rev-parse --git-dir >/dev/null 2>&1 || exit 0
[ "$(git -C "$dir" config --get merge.stat 2>/dev/null)" = "false" ] && exit 0
git -C "$dir" config merge.stat false 2>/dev/null || true
exit 0
