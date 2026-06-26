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
const {
  normalizeArgs,
  shouldAnalyze,
  sectionPlan,
  buildSectionPrompt,
  buildSummaryPrompt,
  collectSiblings,
} = new Function(
  `${m[1]}\nreturn { normalizeArgs, shouldAnalyze, sectionPlan, buildSectionPrompt, buildSummaryPrompt, collectSiblings }`,
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
  contextJson: '{"training_type":"aerobic_base","temperature_c":7.8}',
  activityId: 1,
  activityDate: '2025-10-09',
}

test('buildSectionPrompt inlines CONTEXT and targets only the named section', () => {
  const out = buildSectionPrompt('efficiency', CTX)
  assert.match(out, /<CONTEXT>/)
  assert.match(out, /"training_type":"aerobic_base"/) // real data inlined
  assert.match(out, /ONLY efficiency/)
  assert.match(out, /\/tmp\/analysis_1_2\/efficiency\.json/)
  assert.doesNotMatch(out, /Read\(/) // no file-read dependency
})

test('buildSummaryPrompt inlines CONTEXT and the sibling analysis_data', () => {
  const out = buildSummaryPrompt(CTX, JSON.stringify({ efficiency: { evaluation: 'zone2 ok' } }))
  assert.match(out, /<CONTEXT>/)
  assert.match(out, /<SIBLINGS>/)
  assert.match(out, /"evaluation":"zone2 ok"/)
  assert.match(out, /ONLY summary/)
  assert.match(out, /\/tmp\/analysis_1_2\/summary\.json/)
})

test('collectSiblings maps section -> analysis_data and ignores split/nulls', () => {
  const out = collectSiblings([
    { section: 'efficiency', analysis_data: { a: 1 }, written: true },
    { section: 'phase', analysis_data: { b: 2 }, written: true },
    null, // a dropped agent
    'split agent free-text result', // split returns text, not a section object
    { section: 'environment', analysis_data: { c: 3 }, written: true },
  ])
  assert.deepEqual(out, { efficiency: { a: 1 }, phase: { b: 2 }, environment: { c: 3 } })
})
