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
  buildTempDir,
  TEMP_SUFFIX_PATTERN,
} = new Function(
  `${m[1]}\nreturn { normalizeArgs, planBackfill, shouldAnalyze, sectionPlan, buildSectionPrompt, buildSummaryPrompt, buildTempDir, TEMP_SUFFIX_PATTERN }`,
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

test('test_build_temp_dir_deterministic_path: workflow builds the path from id + suffix', () => {
  assert.equal(buildTempDir(23799768761, '1785501612'), '/tmp/analysis_23799768761_1785501612')
  // a numeric-string activity_id (harness JSON round-trip) yields the same path.
  assert.equal(buildTempDir('23799768761', '1785501612'), '/tmp/analysis_23799768761_1785501612')
})

test('test_build_temp_dir_rejects_shell_expression: unexpanded shell never becomes a path', () => {
  // the exact value the fetch agent returned in #871, which scattered the outputs.
  assert.throws(() => buildTempDir(1, '$(cat /tmp/td_1.txt 2>/dev/null || true)'), /temp_suffix/)
  assert.throws(() => buildTempDir(1, '`date +%s`'), /temp_suffix/)
  assert.throws(() => buildTempDir(1, '$TS'), /temp_suffix/)
})

test('test_build_temp_dir_rejects_placeholder_empty_null: no fallback values', () => {
  for (const bad of ['placeholder', '', ' ', null, undefined, '1785501612 ']) {
    assert.throws(() => buildTempDir(1, bad), /temp_suffix/)
  }
})

test('test_build_temp_dir_rejects_invalid_activity_id: fail fast before analysis', () => {
  for (const bad of [null, undefined, '', 'abc', '12a']) {
    assert.throws(() => buildTempDir(bad, '1785501612'), /activity_id/)
  }
})

test('test_temp_suffix_pattern_matches_digits_only: schema pattern mirrors buildTempDir', () => {
  const re = new RegExp(TEMP_SUFFIX_PATTERN)
  assert.ok(re.test('1785501612'))
  assert.ok(!re.test('placeholder'))
  assert.ok(!re.test('17855_1'))
  assert.ok(!re.test('123')) // shorter than 6 digits => not an epoch
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
