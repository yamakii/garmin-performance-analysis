# Workflow Orchestration

## Plan-First
- Non-trivial tasks (3+ steps or architectural decisions): plan mode
- If execution goes sideways: STOP and re-plan. Don't push through with workarounds.
- Use plan mode for verification steps, not just building

## Implementation
- プラン承認後は `implementation-workflow.md` に従って実行する
- 委任・検証・Ship の手順はすべてそちらに定義

## Self-Improvement Loop
- After ANY user correction: append to `.claude/tasks/lessons.md`
- Format: `- [YYYY-MM-DD] {mistake} -> {correct approach}`
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

## Task Tracking
- Multi-step tasks: plan in `.claude/tasks/todo.md` with checkboxes, track progress, document results.
- Explain changes at each step (high-level summary).

## Core Principles
1. Simplicity First: smallest change that solves the problem.
2. No Laziness: root causes only. No "TODO: fix later" without an Issue.
3. Minimal Impact: unrelated cleanup goes in separate commit.
