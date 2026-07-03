// Automated tests for implement-tier.js pure logic (run by `node --test`).
//
// Workflow scripts run in a sandbox (top-level await/return, injected globals)
// and can't be imported directly, so we extract the side-effect-free block
// between the `// >>> testable` / `// <<< testable` markers and evaluate it.
// This exercises the ACTUAL source (single source of truth) — it would have
// caught the #441 args-as-string regression.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const src = readFileSync(new URL('../implement-tier.js', import.meta.url), 'utf8')
const m = src.match(/\/\/ >>> testable\n([\s\S]*?)\n\s*\/\/ <<< testable/)
assert.ok(m, 'testable block markers not found in implement-tier.js')
// eslint-disable-next-line no-new-func
const { normalizeArgs, mergeDecision, pushCmd, mergeResult } = new Function(
  `${m[1]}\nreturn { normalizeArgs, mergeDecision, pushCmd, mergeResult }`,
)()

test('normalizeArgs parses a JSON string (the #441 regression)', () => {
  const out = normalizeArgs('{"owner":"yamakii","issues":[{"number":1}]}')
  assert.equal(out.owner, 'yamakii')
  assert.equal(out.issues.length, 1)
})

test('normalizeArgs passes objects through and defaults safely', () => {
  assert.deepEqual(normalizeArgs({ a: 1 }), { a: 1 })
  assert.deepEqual(normalizeArgs(undefined), {})
  assert.deepEqual(normalizeArgs('not json'), {})
})

const GREEN = {
  validation: { status: 'pass' },
  ship: { ci_conclusion: 'success', mergeable: true, pr_number: 1 },
}

test('mergeDecision auto-merges .claude/workflows and hooks when green', () => {
  for (const f of ['.claude/workflows/x.js', '.claude/hooks/y.sh']) {
    const d = mergeDecision({ manifest: { changed_files: [f] }, ...GREEN })
    assert.equal(d.ok, true, `${f} should auto-merge when green`)
  }
})

test('mergeDecision still escalates L3 agent definitions', () => {
  const d = mergeDecision({
    manifest: { changed_files: ['.claude/agents/z-analyst.md'] },
    validation: { status: 'pass', level: 'L3' },
    ship: GREEN.ship,
  })
  assert.equal(d.ok, false, 'L3 should escalate')
})

test('mergeDecision allows normal green code/doc changes', () => {
  assert.equal(
    mergeDecision({ manifest: { changed_files: ['packages/x.py'] }, ...GREEN }).ok,
    true,
  )
  assert.equal(
    mergeDecision({ manifest: { changed_files: ['docs/x.md'] }, ...GREEN }).ok,
    true,
  )
})

test('mergeDecision blocks on failed validation / ci / conflict', () => {
  const base = { manifest: { changed_files: ['packages/x.py'] } }
  assert.equal(
    mergeDecision({ ...base, validation: { status: 'fail' }, ship: GREEN.ship }).ok,
    false,
  )
  assert.equal(
    mergeDecision({
      ...base,
      validation: { status: 'pass' },
      ship: { ci_conclusion: 'failure', mergeable: true, pr_number: 1 },
    }).ok,
    false,
  )
  assert.equal(
    mergeDecision({
      ...base,
      validation: { status: 'pass' },
      ship: { ci_conclusion: 'success', mergeable: false, pr_number: 1 },
    }).ok,
    false,
  )
})

test('test_merge_failure_reason_uses_error: merge:false surfaces mg.error', () => {
  const out = mergeResult('検証 PASS + ci-guard success + mergeable', { merged: false, error: 'boom' })
  assert.equal(out.merged, false)
  assert.ok(out.reason.includes('boom'), 'reason should surface the merge error, not the green sentence')
  assert.equal(out.merge_sha, null)
})

test('test_merge_failure_reason_uses_error: falls back when no error given', () => {
  const out = mergeResult('検証 PASS + ci-guard success + mergeable', { merged: false })
  assert.equal(out.merged, false)
  assert.equal(out.reason, 'merge_pull_request 失敗')
})

test('test_merge_success_keeps_green_reason: merge:true keeps decision reason', () => {
  const out = mergeResult('検証 PASS + ci-guard success + mergeable', { merged: true, merge_sha: 'abc123' })
  assert.equal(out.merged, true)
  assert.equal(out.reason, '検証 PASS + ci-guard success + mergeable')
  assert.equal(out.merge_sha, 'abc123')
})

test('pushCmd embeds a credential.helper feeding GITHUB_TOKEN', () => {
  const cmd = pushCmd('/wt/path', 'feature/xyz')
  assert.ok(cmd.includes('credential.helper'), 'push command must inject a credential helper')
  assert.ok(cmd.includes('GITHUB_TOKEN'), 'helper must feed GITHUB_TOKEN')
  assert.ok(cmd.includes('push -u origin feature/xyz'), 'push must target the branch')
  assert.ok(!cmd.includes('${'), 'no unresolved template placeholders')
})
