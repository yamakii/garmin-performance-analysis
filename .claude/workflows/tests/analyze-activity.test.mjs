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
  planBackfill,
  shouldAnalyze,
  sectionPlan,
  buildSectionPrompt,
  buildSummaryPrompt,
} = new Function(
  `${m[1]}\nreturn { normalizeArgs, planBackfill, shouldAnalyze, sectionPlan, buildSectionPrompt, buildSummaryPrompt }`,
)()

test('normalizeArgs accepts a bare date string', () => {
  assert.deepEqual(normalizeArgs('2025-10-09'), { date: '2025-10-09', dates: null })
})

test('normalizeArgs accepts an object and empty/undefined', () => {
  assert.deepEqual(normalizeArgs({ date: '2025-10-09' }), { date: '2025-10-09', dates: null })
  assert.deepEqual(normalizeArgs('{"date":"2025-10-09"}'), { date: '2025-10-09', dates: null })
  assert.deepEqual(normalizeArgs(undefined), { date: null, dates: null })
  assert.deepEqual(normalizeArgs(''), { date: null, dates: null })
  assert.deepEqual(normalizeArgs({}), { date: null, dates: null })
})

test('parseArgs が dates 配列を受理する', () => {
  // backfill mode: a non-empty dates array is parsed and takes precedence.
  assert.deepEqual(normalizeArgs('{"dates":["2026-06-01","2026-06-02"]}'), {
    date: null,
    dates: ['2026-06-01', '2026-06-02'],
  })
  assert.deepEqual(normalizeArgs({ dates: ['2026-06-01', '2026-06-02'] }), {
    date: null,
    dates: ['2026-06-01', '2026-06-02'],
  })
  // an empty dates array falls back to single-date (null) mode.
  assert.deepEqual(normalizeArgs({ dates: [] }), { date: null, dates: null })
})

test('cap 超過時に残数を返す', () => {
  const seven = ['d1', 'd2', 'd3', 'd4', 'd5', 'd6', 'd7']
  const { toRun, remaining } = planBackfill(seven) // default cap = 5
  assert.equal(toRun.length, 5)
  assert.deepEqual(toRun, ['d1', 'd2', 'd3', 'd4', 'd5'])
  assert.equal(remaining, 2)
  // within cap: nothing deferred.
  assert.deepEqual(planBackfill(['a', 'b']), { toRun: ['a', 'b'], remaining: 0 })
})

test('shouldAnalyze gates on has_run', () => {
  assert.equal(shouldAnalyze({ has_run: true }), true)
  assert.equal(shouldAnalyze({ has_run: false }), false)
  assert.equal(shouldAnalyze(null), false)
  assert.equal(shouldAnalyze(undefined), false)
})

test('sectionPlan puts all 4 unified sections (incl. summary) in one barrier', () => {
  const p = sectionPlan()
  assert.deepEqual(p.unified, ['efficiency', 'phase', 'environment', 'summary'])
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

test('buildSummaryPrompt inlines CONTEXT and derives consistency from it (no siblings)', () => {
  const out = buildSummaryPrompt(CTX)
  assert.match(out, /<CONTEXT>/)
  assert.match(out, /"training_type":"aerobic_base"/) // real data inlined
  assert.match(out, /zone_distribution_rating|form_evaluation/) // CONTEXT-based consistency
  assert.match(out, /ONLY summary/)
  assert.match(out, /\/tmp\/analysis_1_2\/summary\.json/)
  assert.doesNotMatch(out, /<SIBLINGS>/) // no sibling JSONs in parallel mode
})
