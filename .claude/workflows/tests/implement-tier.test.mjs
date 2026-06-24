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
const { normalizeArgs, mergeDecision } = new Function(
  `${m[1]}\nreturn { normalizeArgs, mergeDecision }`,
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
