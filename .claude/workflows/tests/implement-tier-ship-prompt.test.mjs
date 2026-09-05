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
