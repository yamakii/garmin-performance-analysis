// Automated tests for analyze-activity.js pure logic (run by `node --test`).
//
// Workflow scripts run in a sandbox (top-level await/return, injected globals)
// and can't be imported directly, so we extract the side-effect-free block
// between the `// >>> testable` / `// <<< testable` markers and evaluate it.
// This exercises the ACTUAL source (single source of truth).
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const src = readFileSync(new URL('../analyze-activity.js', import.meta.url), 'utf8')
const m = src.match(/\/\/ >>> testable\n([\s\S]*?)\n\s*\/\/ <<< testable/)
assert.ok(m, 'testable block markers not found in analyze-activity.js')
// eslint-disable-next-line no-new-func
const { normalizeArgs, shouldAnalyze, sectionPlan, buildSectionPrompt, buildSummaryPrompt } = new Function(
  `${m[1]}\nreturn { normalizeArgs, shouldAnalyze, sectionPlan, buildSectionPrompt, buildSummaryPrompt }`,
)()

test('normalizeArgs accepts a bare date string', () => {
  assert.deepEqual(normalizeArgs('2025-10-09'), { date: '2025-10-09' })
})

test('normalizeArgs accepts an object and empty/undefined', () => {
  assert.deepEqual(normalizeArgs({ date: '2025-10-09' }), { date: '2025-10-09' })
  assert.deepEqual(normalizeArgs('{"date":"2025-10-09"}'), { date: '2025-10-09' })
  assert.deepEqual(normalizeArgs(undefined), { date: null })
  assert.deepEqual(normalizeArgs(''), { date: null })
  assert.deepEqual(normalizeArgs({}), { date: null })
})

test('shouldAnalyze gates on has_run', () => {
  assert.equal(shouldAnalyze({ has_run: true }), true)
  assert.equal(shouldAnalyze({ has_run: false }), false)
  assert.equal(shouldAnalyze(null), false)
  assert.equal(shouldAnalyze(undefined), false)
})

test('sectionPlan splits independent group, dependent summary, and split', () => {
  const p = sectionPlan()
  assert.deepEqual(p.independent, ['efficiency', 'phase', 'environment'])
  assert.equal(p.dependent, 'summary')
  assert.equal(p.extra, 'split')
})

const CTX = {
  tempDir: '/tmp/analysis_1_2',
  contextPath: '/tmp/ctx_1_2.json',
  activityId: 1,
  activityDate: '2025-10-09',
}

test('buildSectionPrompt targets only the named section and reads the context file', () => {
  const out = buildSectionPrompt('efficiency', CTX)
  assert.match(out, /efficiency/)
  assert.match(out, /\/tmp\/ctx_1_2\.json/) // CONTEXT lives OUTSIDE the merge dir
  assert.match(out, /ONLY efficiency/)
  assert.match(out, /\/tmp\/analysis_1_2\/efficiency\.json/)
  assert.doesNotMatch(out, /\/tmp\/analysis_1_2\/context\.json/) // never inside temp_dir
})

test('buildSectionPrompt forbids fabrication when the context cannot be read', () => {
  const out = buildSectionPrompt('environment', CTX)
  assert.match(out, /捏造/)
  assert.match(out, /context 読込失敗|読込失敗/)
})

test('buildSummaryPrompt reads the three sibling section JSONs for consistency', () => {
  const out = buildSummaryPrompt(CTX)
  assert.match(out, /\/tmp\/ctx_1_2\.json/)
  assert.match(out, /\/tmp\/analysis_1_2\/efficiency\.json/)
  assert.match(out, /\/tmp\/analysis_1_2\/phase\.json/)
  assert.match(out, /\/tmp\/analysis_1_2\/environment\.json/)
  assert.match(out, /ONLY summary/)
})
