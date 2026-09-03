# Workflow Orchestration

## Plan-First
- Non-trivial tasks (3+ steps or architectural decisions): plan mode
- If execution goes sideways: STOP and re-plan. Don't push through with workarounds.
- Use plan mode for verification steps, not just building

## Implementation
- プラン承認後は `implementation-workflow.md` に従って実行する
- 委任・検証・Ship の手順はすべてそちらに定義
- **全変更で Worktree → PR が必須**。Validation Level: skip は検証方法の指定であり、ワークフロー省略の許可ではない

## Self-Improvement Loop
- After ANY user correction: append to `.claude/tasks/lessons.md`
- Format: `- [YYYY-MM-DD] {mistake} -> {correct approach}`
- **lessons.md はルール昇格前の一時バッファ**（恒久ルールの正本ではない）。溜めっぱなしにせず定期的に triage する:
  再発防止をルール化できる教訓は `.claude/rules/` に昇格させ、一度きり・陳腐化したものは破棄する。
  棚卸しの手順は `/project-status` の Step 5 に組み込まれている
- lessons.md / settings.local.json は **git 管理外**。背景ジョブでは bg-isolation guard が shared checkout への
  Edit/Write を拒否するため、これらの追記・削除は **Bash 経由の `uv run python`** で行う（python 直叩き・Edit は不可）
- Write rules in `.claude/rules/` that prevent the same mistake from recurring
- Ruthlessly iterate until mistake rate drops
- セッション開始時: lessons.md を確認し、関連する過去の教訓を意識する

## Elegance Check
- 3+ files changed or new pattern introduced: pause and consider alternatives.
- If a fix feels hacky: step back and implement the elegant solution with full context.
- Simple fixes (typos, single-line, config): skip.

## Bug Fix Autonomy
- Bug reports: diagnose root cause, fix, verify. No hand-holding.
- Failing CI: fix without being told. Point at logs → resolve.
- Zero context switching required from the user.

## Autonomy Boundaries
- **外部副作用は毎回確認する**。PR マージの恒久承認（#886）はマージにしか及ばない。以下は別枠で、実行前にユーザーの確認を取る:
  - Garmin Connect への書き込み（`schedule_custom_workout` / `cleanup_generated_workouts(dry_run=False)` 等のカレンダー・ワークアウト変更）
  - cloud routine / scheduled agent / cron の作成・変更（`/schedule`, `/loop`, CronCreate）
  - GitHub リポジトリ設定の変更（branch protection, auto-merge, Dependabot, Actions 設定, secrets）
  - DB の削除・全件再生成（`--delete-db`, テーブル drop, `rm` を伴う data/ の操作）
- ユーザーの直接依頼がその操作自体であれば（例:「今日のロングランを Garmin に登録して」）、その **1 操作だけ**は依頼をもって承認済みとみなす。付随して発生する他の書き込み・削除・設定変更は都度確認する
- 背景ジョブ・非対話セッションでも同じ。確認が取れないなら、その操作を残して他を完了し、報告で `needs input:` として明示する
- 根拠: 2026-09-02 の保守セッションでユーザーが「定期ルーチン化以外は進めて」と明示的に切り分けた（cloud routine 作成は恒久承認の範囲外）

## Task Tracking
- Multi-step tasks: plan in `.claude/tasks/todo.md` with checkboxes, track progress, document results.
- Explain changes at each step (high-level summary).

## Core Principles
1. Simplicity First: smallest change that solves the problem.
2. No Laziness: root causes only. No "TODO: fix later" without an Issue.
3. Minimal Impact: unrelated cleanup goes in separate commit.
