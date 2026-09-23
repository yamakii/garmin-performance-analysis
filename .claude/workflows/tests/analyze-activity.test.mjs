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
  buildRunNoteContext,
  buildRunNotePrompt,
  summarizeRun,
  buildTempDir,
  TEMP_SUFFIX_PATTERN,
} = new Function(
  `${m[1]}\nreturn { normalizeArgs, planBackfill, shouldAnalyze, sectionPlan, buildRunNoteContext, buildRunNotePrompt, summarizeRun, buildTempDir, TEMP_SUFFIX_PATTERN }`,
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

test('builds one analysis task named run_note', () => {
  const plan = sectionPlan()
  assert.equal(plan.length, 1)
  assert.deepEqual(plan, ['run_note'])
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

// The 2026-09-18 bundle, trimmed to the keys the subset cares about plus two
// large keys that must NOT reach the run-note agent (the page already renders
// the baselines and zone tables).
const BUNDLE = JSON.stringify({
  activity_id: 24407019887,
  activity_date: '2026-09-18',
  training_type: 'easy',
  week_position: { is_long_run_day: false, days_to_long_run: 3, cutback_week: false },
  prescription_for_run: {
    prescription_id: 61,
    session_type: 'easy',
    title: 'イージー 8km',
    target_km: 8.0,
    target_minutes: 50,
    hr_low: 130,
    hr_high: 150,
    rationale: '週末のロングに向けて脚を回復させる',
    garmin_workout_id: 1691891896,
  },
  prescription_verdict: { verdict: '✅', reasons: ['処方どおりに実施できています'] },
  morning_wellness: { readiness: 72, rhr_z: -0.4 },
  vs_previous: { pace_delta_s_per_km: -6.0 },
  previous_same_type: { activity_id: 24300000001, activity_date: '2026-09-15' },
  similar_workouts: {
    similar_activities: [{ activity_id: 1 }, { activity_id: 2 }, { activity_id: 3 }, { activity_id: 4 }],
  },
  gear: { gear_uuid: 'abc', gear_nickname: 'v15', total_km: 412.0 },
  long_run_gate: null,
  form_baseline_trend: { metrics: { gct: { current: { coef_d: -2.26 } } } },
  hr_zones_detail: { zones: [{ zone_number: 2, low_boundary: 130, high_boundary: 150 }] },
})

const REPORT = JSON.stringify({
  activity_id: 24407019887,
  activity_date: '2026-09-18',
  headline: { label: '処方どおり' },
  signals: [{ metric: 'gct', status: 'within', adverse: false }],
  moments: [{ id: 'm1', kind: 'steady', split_index: 1 }],
  conditions: { temp_c: 24.1 },
})

const CTX = {
  tempDir: '/tmp/analysis_1_2',
  contextJson: BUNDLE,
  reportJson: REPORT,
  activityId: 1,
  activityDate: '2026-09-18',
}

test('run-note prompt inlines the report and the context subset', () => {
  const out = buildRunNotePrompt(CTX)
  assert.match(out, /<REPORT>/)
  assert.match(out, /"moments"/) // the scenes the timeline must key on
  assert.match(out, /<CONTEXT>/)
  assert.match(out, /"week_position"/) // why the day was prescribed
  assert.match(out, /"rationale":"週末のロングに向けて脚を回復させる"/)
  assert.match(out, /ONLY run_note/)
  assert.match(out, /\/tmp\/analysis_1_2\/run_note\.json/)
  // Bulk keys the figures already render stay out of the prompt.
  assert.doesNotMatch(out, /form_baseline_trend/)
  assert.doesNotMatch(out, /hr_zones_detail/)
  assert.doesNotMatch(out, /Read\(/) // no file-read dependency
})

test('test_buildRunNoteContext_keeps_only_the_coach_subset', () => {
  const out = JSON.parse(buildRunNoteContext(BUNDLE))
  assert.equal(out.training_type, 'easy')
  assert.equal(out.week_position.days_to_long_run, 3)
  assert.equal(out.prescription_for_run.hr_high, 150)
  // A bundle's own verdict never reaches the analyst: REPORT.plan is the one
  // plan verdict (#1353), and an older bundle that still carries one is ignored.
  assert.equal(out.prescription_verdict, undefined)
  assert.equal(out.morning_wellness.readiness, 72)
  assert.equal(out.previous_same_type.activity_date, '2026-09-15')
  assert.equal(out.gear.gear_nickname, 'v15')
  // Top 3 similar workouts only — this is context for one sentence, not a table.
  assert.equal(out.similar_workouts.length, 3)
  // Row bookkeeping and page-rendered bulk stay out.
  assert.equal(out.prescription_for_run.garmin_workout_id, undefined)
  assert.equal(out.form_baseline_trend, undefined)
  assert.equal(out.hr_zones_detail, undefined)
})

test('test_buildRunNoteContext_returns_empty_string_for_unparsable_json', () => {
  assert.equal(buildRunNoteContext('{'), '')
  assert.equal(buildRunNoteContext(undefined), '')
  assert.equal(buildRunNoteContext('null'), '')
})

test('test_buildRunNotePrompt_falls_back_without_context', () => {
  const out = buildRunNotePrompt({ ...CTX, contextJson: '{' })
  assert.doesNotMatch(out, /<CONTEXT>/)
  assert.match(out, /<REPORT>/) // the report alone still grounds the review
  assert.match(out, /\/tmp\/analysis_1_2\/run_note\.json/)
})

test('summarises result with run_note only', () => {
  const out = summarizeRun(
    { activity_id: 24407019887, activity_date: '2026-09-18' },
    { succeeded: ['run_note'], failed: [], errors: [] },
  )
  assert.equal(out.status, 'done')
  assert.equal(out.activity_id, 24407019887)
  assert.equal(out.activity_date, '2026-09-18')
  assert.deepEqual(out.succeeded, ['run_note'])
  assert.deepEqual(out.failed, [])
  assert.deepEqual(out.errors, [])
})

test('test_summarizeRun_reports_a_rejected_run_note', () => {
  const out = summarizeRun(
    { activity_id: 1, activity_date: '2026-09-18' },
    { succeeded: [], failed: ['run_note'], errors: ['run_note: timeline moment_id ...'] },
  )
  assert.deepEqual(out.succeeded, [])
  assert.deepEqual(out.failed, ['run_note'])
  assert.equal(out.errors.length, 1)
})

test('test_summarizeRun_tolerates_a_missing_merge_payload', () => {
  const out = summarizeRun({ activity_id: 1, activity_date: '2026-09-18' }, undefined)
  assert.deepEqual(out.succeeded, [])
  assert.deepEqual(out.failed, [])
  assert.deepEqual(out.errors, [])
})
