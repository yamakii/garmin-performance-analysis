# Workflow Orchestration

## Plan-First
- Non-trivial tasks (3+ steps or architectural decisions): plan mode
- If execution goes sideways: STOP and re-plan. Don't push through with workarounds.

## Subagent Delegation
- Offload research/exploration to subagents. Keep main context clean.
- One focused task per subagent.

## Completion Verification
- Never mark complete without proof: passing tests, log output, or demonstration.
- Extends `real-data-validation.md` for data-specific checks.

## Elegance Check
- 3+ files changed or new pattern introduced: pause and consider alternatives.
- Simple fixes (typos, single-line, config): skip.

## Bug Fix Autonomy
- Bug reports: diagnose root cause, fix, verify. No hand-holding.
- Ask user only when ambiguous (multiple root causes, unclear expected behavior).

## Core Principles
1. Simplicity First: smallest change that solves the problem.
2. No Laziness: root causes only. No "TODO: fix later" without an Issue.
3. Minimal Impact: unrelated cleanup goes in separate commit.

## Lesson Capture
- After user correction: append to `.claude/tasks/lessons.md`
- Format: `- [YYYY-MM-DD] {mistake} -> {correct approach}`

## Task Tracking
- Multi-step tasks: track in `.claude/tasks/todo.md` with checkboxes
