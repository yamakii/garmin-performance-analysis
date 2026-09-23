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
  fetchPrompt,
  buildRunNotePrompt,
  summarizeRun,
  buildTempDir,
  TEMP_SUFFIX_PATTERN,
  RUN_NOTE_EFFORT,
} = new Function(
  `${m[1]}\nreturn { normalizeArgs, planBackfill, shouldAnalyze, sectionPlan, fetchPrompt, buildRunNotePrompt, summarizeRun, buildTempDir, TEMP_SUFFIX_PATTERN, RUN_NOTE_EFFORT }`,
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

const CTX = {
  tempDir: '/tmp/analysis_1_2',
  activityId: 24407019887,
  activityDate: '2026-09-18',
}

test('test_buildRunNotePrompt_has_the_analyst_fetch_its_own_inputs', () => {
  const out = buildRunNotePrompt(CTX)
  // One MCP call for both inputs, addressed to this activity (#1362).
  assert.match(out, /mcp__garmin-db__get_run_note_inputs\(activity_id=24407019887\)/)
  assert.match(out, /report を REPORT、context を CONTEXT/)
  // Nothing is inlined any more: the fetch stage no longer re-types the JSON.
  assert.doesNotMatch(out, /<REPORT>/)
  assert.doesNotMatch(out, /<CONTEXT>/)
  assert.match(out, /ONLY run_note/)
  assert.match(out, /\/tmp\/analysis_1_2\/run_note\.json/)
  assert.doesNotMatch(out, /Read\(/) // no file-read dependency
})

test('test_run_note_agent_runs_at_medium_effort', () => {
  // Explicit, not inherited from the session (#1364): the review is written by
  // opus (agent def) at medium effort, and the Analyze call must pass it.
  assert.equal(RUN_NOTE_EFFORT, 'medium')
  assert.match(src, /agentType: 'run-note-analyst',\n\s*effort: RUN_NOTE_EFFORT,/)
  const def = readFileSync(new URL('../../agents/run-note-analyst.md', import.meta.url), 'utf8')
  assert.match(def, /^model: opus$/m)
})

test('test_fetchPrompt_calls_the_mcp_tools_directly', () => {
  // #1366: haiku routed around the deferred MCP tools via Bash/python.
  const out = fetchPrompt('2026-09-18')
  assert.match(out, /MCP ツールの呼び出しそのもの/)
  assert.match(out, /Bash・python・スクリプト・CLI で代替/)
})

test('test_fetchPrompt_surfaces_catch_up_errors', () => {
  // #1366: a failed catch-up must never read as "no new data".
  const out = fetchPrompt('2026-09-18')
  assert.match(out, /そのドメインとエラー名を catch_up_summary に必ず書く/)
  assert.match(out, /エラーを「差分なし」と書かない/)
})

test('test_fetch_agent_runs_on_sonnet', () => {
  const call = src.slice(src.indexOf("label: 'fetch',"), src.indexOf('schema: FETCH_SCHEMA'))
  assert.match(call, /\n\s*model: 'sonnet',/)
})

test('test_fetchPrompt_only_ingests', () => {
  const out = fetchPrompt('2026-09-18')
  assert.match(out, /catch_up_ingest\(end_date="2026-09-18"\)/)
  assert.match(out, /ingest_activity\(date="2026-09-18"\)/)
  assert.match(out, /date \+%s/)
  // The prefetch payloads are the analyst's to fetch, not this stage's.
  assert.doesNotMatch(out, /prefetch_activity_context/)
  assert.doesNotMatch(out, /prefetch_run_report/)
  assert.doesNotMatch(out, /context_json|report_json/)
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
