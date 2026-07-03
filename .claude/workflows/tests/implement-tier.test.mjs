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
const { normalizeArgs, mergeDecision, pushCmd, mergeResult, levelFromChangedFiles } = new Function(
  `${m[1]}\nreturn { normalizeArgs, mergeDecision, pushCmd, mergeResult, levelFromChangedFiles }`,
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

const GREEN_SHIP = { ci_conclusion: 'success', mergeable: true, pr_number: 1 }

// Build a fully-green acc whose declared level matches the changed_files verdict
// (so the under-declaration guard passes) unless `level` is overridden.
function greenAcc(changed_files, level = levelFromChangedFiles(changed_files)) {
  return {
    manifest: { changed_files, validation_level: level },
    validation: { status: 'pass', level },
    ship: { ...GREEN_SHIP },
  }
}

test('test_level_from_changed_files_table maps representative paths', () => {
  assert.equal(levelFromChangedFiles(['.claude/agents/z-analyst.md']), 'L3')
  assert.equal(levelFromChangedFiles(['packages/garmin-mcp-server/src/garmin_mcp/database/readers/splits.py']), 'L1')
  assert.equal(levelFromChangedFiles(['packages/garmin-mcp-server/src/garmin_mcp/tools/performance.py']), 'L1')
  assert.equal(levelFromChangedFiles(['packages/garmin-web/frontend/src/App.tsx']), 'L2')
  assert.equal(levelFromChangedFiles(['packages/garmin-mcp-server/src/garmin_mcp/ingest/worker.py']), 'L2')
  assert.equal(levelFromChangedFiles(['.claude/rules/dev/x.md']), 'skip')
  assert.equal(levelFromChangedFiles(['docs/x.md']), 'skip')
  assert.equal(levelFromChangedFiles(['CLAUDE.md']), 'skip')
  assert.equal(levelFromChangedFiles([]), 'skip')
  // mixed → highest level wins
  assert.equal(
    levelFromChangedFiles(['docs/x.md', 'src/garmin_mcp/ingest/worker.py', 'src/garmin_mcp/database/readers/y.py']),
    'L2',
  )
  assert.equal(levelFromChangedFiles(['docs/x.md', '.claude/agents/z-analyst.md']), 'L3')
})

test('test_matching_level_merges: 申告 L2 + web change + all-green → ok', () => {
  const acc = greenAcc(['packages/garmin-web/frontend/src/App.tsx'], 'L2')
  const d = mergeDecision(acc)
  assert.equal(d.ok, true, 'matching declared level with green gates should merge')
})

test('test_undeclared_higher_level_escalates: 申告 L1 + ingest change → escalate', () => {
  const d = mergeDecision({
    manifest: {
      changed_files: ['packages/garmin-mcp-server/src/garmin_mcp/ingest/worker.py'],
      validation_level: 'L1',
    },
    validation: { status: 'pass', level: 'L1' },
    ship: { ...GREEN_SHIP },
  })
  assert.equal(d.ok, false, 'under-declared L1 (computed L2) must escalate')
  assert.match(d.reason, /過小申告/)
  assert.match(d.reason, /申告 L1 \/ 判定 L2/)
})

test('mergeDecision auto-merges .claude/workflows and hooks when green', () => {
  // workflows/hooks are unknown paths → computed L2; declaring L2 keeps them green.
  for (const f of ['.claude/workflows/x.js', '.claude/hooks/y.sh']) {
    const d = mergeDecision(greenAcc([f], 'L2'))
    assert.equal(d.ok, true, `${f} should auto-merge when green`)
  }
})

test('mergeDecision still escalates L3 agent definitions', () => {
  const d = mergeDecision({
    manifest: { changed_files: ['.claude/agents/z-analyst.md'], validation_level: 'L3' },
    validation: { status: 'pass', level: 'L3' },
    ship: GREEN_SHIP,
  })
  assert.equal(d.ok, false, 'L3 should escalate')
})

test('mergeDecision allows normal green code/doc changes', () => {
  assert.equal(mergeDecision(greenAcc(['packages/x.py'], 'L2')).ok, true)
  assert.equal(mergeDecision(greenAcc(['docs/x.md'], 'skip')).ok, true)
})

test('mergeDecision blocks on failed validation / ci / conflict', () => {
  const files = ['packages/x.py']
  assert.equal(
    mergeDecision({
      manifest: { changed_files: files, validation_level: 'L2' },
      validation: { status: 'fail', level: 'L2' },
      ship: GREEN_SHIP,
    }).ok,
    false,
  )
  assert.equal(
    mergeDecision({
      manifest: { changed_files: files, validation_level: 'L2' },
      validation: { status: 'pass', level: 'L2' },
      ship: { ci_conclusion: 'failure', mergeable: true, pr_number: 1 },
    }).ok,
    false,
  )
  assert.equal(
    mergeDecision({
      manifest: { changed_files: files, validation_level: 'L2' },
      validation: { status: 'pass', level: 'L2' },
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
