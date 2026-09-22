// Regression guard for #993: the Ship-stage prompt must make the CI wait a
// single FOREGROUND `wait-for-ci.sh` call. When the instruction was vague the
// sonnet agent backgrounded the script and improvised a `pgrep`/`kill -0`
// Monitor, which trips the `Bash(kill:*)` ask rule and stalls the tier with a
// permission prompt. The prompt lives outside the `// >>> testable` block
// (it is built inside the stage closure), so this test asserts on the source
// text of that stage directly.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const src = readFileSync(new URL('../implement-tier.js', import.meta.url), 'utf8')
const shipStage = src.match(/\/\/ Stage 3[\s\S]*?\/\/ Stage 4/)
assert.ok(shipStage, 'Stage 3 (Ship) block not found in implement-tier.js')
const prompt = shipStage[0]

test('ship prompt waits for CI in the foreground with wait-for-ci.sh', () => {
  assert.match(prompt, /wait-for-ci\.sh PR番号 --timeout 900/)
  assert.match(prompt, /フォアグラウンド/)
})

test('ship prompt forbids background/process-watcher workarounds', () => {
  for (const banned of ['run_in_background', 'Monitor', 'pgrep', 'kill']) {
    assert.ok(prompt.includes(banned), `prompt must name "${banned}" as forbidden`)
  }
  assert.match(prompt, /使わない/)
})

// Regression guard for #1130 / #1304: pushed history is never rewritten, so a
// conflicting sibling merge is resolved by a merge commit (never rebase + force
// push, which stalled Epic #1115 Tier 2 on permission prompts). The merge runs
// only on conflict and quietly: a pre-push catch-up merge printed a full
// diffstat into the agent context on every ship (#1304).
test('test_ship_prompt_merges_instead_of_rebasing', () => {
  assert.match(prompt, /merge -q --no-stat --no-edit origin\/main/)
  assert.match(prompt, /merge --abort/)
  assert.doesNotMatch(prompt, /rebase してから/)
  assert.doesNotMatch(prompt, /git rebase origin/)
})

test('test_ship_prompt_merges_only_on_conflict', () => {
  assert.match(prompt, /事前取り込みはしない/)
  assert.match(prompt, /false（コンフリクト）のときだけ/)
  assert.doesNotMatch(prompt, /遅れていれば先に/)
})
