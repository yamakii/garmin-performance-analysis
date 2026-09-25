// Regression guard for #1424: the Merge-stage agent must be told where its
// authority to merge comes from. Without it, a sonnet merge agent read the
// relayed user message (unrelated to merging) as the only authoritative voice
// and refused a PR that had already passed the gate (PR #1410, Epic #1398).
// The prompt lives outside the `// >>> testable` block (it is built inside the
// stage closure), so this test asserts on the source text of that stage.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const src = readFileSync(new URL('../implement-tier.js', import.meta.url), 'utf8')
const mergeStage = src.match(/\/\/ Stage 4[\s\S]*?\/\/ ── summary/)
assert.ok(mergeStage, 'Stage 4 (Merge) block not found in implement-tier.js')
const prompt = mergeStage[0]

test('test_merge_prompt_cites_standing_approval', () => {
  assert.ok(prompt.includes('#886'), 'prompt must cite the standing approval #886')
  assert.ok(prompt.includes('worktree-validation-protocol.md §6'), 'prompt must point at the gate rule')
  assert.ok(prompt.includes('/implement'), 'prompt must name the /implement opt-in')
  assert.ok(prompt.includes('mergeDecision'), 'prompt must say the gate was decided in code')
})

test('test_merge_prompt_keeps_bypass_prohibition', () => {
  assert.match(prompt, /権限システム迂回/)
  assert.match(prompt, /MCP tool 経由/)
})
