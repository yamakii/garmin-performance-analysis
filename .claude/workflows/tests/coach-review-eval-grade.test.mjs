// Unit tests for the deterministic graders and the case loader of the
// coach-review eval (.claude/hillclimb/coach-review/). Synthetic data only - no
// athlete data. The judge (a model call) is exercised only with a stub.
import assert from 'node:assert/strict'
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import { caseEnv, combine, deterministicChecks, garminToolsReached, judge } from '../../hillclimb/coach-review/grade.mjs'
import { caseProblem, loadCases, loadRunNotePrompt, toolPermissions } from '../../hillclimb/coach-review/run-eval.mjs'

const REPORT = {
  moments: [
    { id: 'm1', kind: 'fast_start', split_index: 1 },
    { id: 'm2', kind: 'hr_ceiling_touch', split_index: 4 },
  ],
}

function note(overrides = {}) {
  return {
    story: '週の中盤に置いたつなぎのランで、狙いどおり脚を回復させながら距離を踏めています。',
    good_points: [{ text: '処方の距離をそのまま守り切れています。', evidence: 'plan.volume' }],
    growth_points: [{ text: '終盤で上限心拍に触れた分、抑える余地があります。', evidence: 'plan.hr_ceiling' }],
    next_challenge: '上限の150に近づく前に意識してペースを抑えましょう。',
    next_challenge_evidence: 'plan.hr_ceiling',
    timeline: [{ moment_id: 'm2', text: '4km地点で上限心拍に触れましたが、立て直せています。' }],
    notes: [],
    question: null,
    ...overrides,
  }
}

const runNoteCase = (expect) => ({ id: 'c1', kind: 'run_note', pattern: 'A', activity_id: 1, date: '2026-01-01', expect })
const PY_OK = { schema_ok: true, grounding_ok: true, errors: [] }

test('test_forbid_regex_flags_match', () => {
  const kase = runNoteCase({ forbid_regex: ['最初の1km.*ゆっくり'] })
  const n = note({ next_challenge: '最初の1kmをもっとゆっくり入りましょう。' })
  const det = deterministicChecks(kase, n, REPORT, { pyCheck: PY_OK })
  assert.equal(det.forbid_regex_ok, false)
  assert.equal(deterministicChecks(kase, note(), REPORT, { pyCheck: PY_OK }).forbid_regex_ok, true)
  // conversation answers are checked the same way
  const conv = { id: 'q', kind: 'conversation', pattern: 'A', prompt: '?', expect: { forbid_regex: ['最初の1km.*ゆっくり'] } }
  assert.equal(deterministicChecks(conv, '最初の1kmをもっとゆっくり').forbid_regex_ok, false)
})

test('test_growth_point_kind_forbidden', () => {
  const kase = runNoteCase({ forbid_growth_point_moment_kinds: ['fast_start'] })
  const bad = note({ growth_points: [{ text: '入りが速すぎました。', evidence: 'moments.m1' }] })
  const det = deterministicChecks(kase, bad, REPORT, { pyCheck: PY_OK })
  assert.equal(det.growth_point_kinds_ok, false)
  assert.match(det.why.growth_point_kinds_ok, /moments\.m1 \(fast_start\)/)
  const fine = note({ growth_points: [{ text: '上限に触れました。', evidence: 'moments.m2' }] })
  assert.equal(deterministicChecks(kase, fine, REPORT, { pyCheck: PY_OK }).growth_point_kinds_ok, true)
})

test('test_required_evidence_prefix_missing', () => {
  const kase = runNoteCase({ required_evidence_prefixes: ['context.athlete_context'] })
  assert.equal(deterministicChecks(kase, note(), REPORT, { pyCheck: PY_OK }).required_evidence_ok, false)
  const cited = note({ good_points: [{ text: '前日の文脈を踏まえています。', evidence: 'context.athlete_context' }] })
  assert.equal(deterministicChecks(kase, cited, REPORT, { pyCheck: PY_OK }).required_evidence_ok, true)
  // a section payload (analysis_data wrapper) is read the same way
  assert.equal(deterministicChecks(kase, { analysis_data: cited }, REPORT, { pyCheck: PY_OK }).required_evidence_ok, true)
})

test('test_conversation_case_nulls_run_note_checks', () => {
  const kase = { id: 'q', kind: 'conversation', pattern: 'E', prompt: '今日はどうでしたか？', expect: {} }
  const det = deterministicChecks(kase, '今日は処方どおりでした。', null)
  assert.equal(det.schema_ok, null)
  assert.equal(det.grounding_ok, null)
  assert.equal(det.growth_point_kinds_ok, null)
  assert.equal(det.required_evidence_ok, null)
  assert.equal(det.forbid_regex_ok, null)
  assert.equal(det.output_ok, true)
})

test('test_run_note_missing_output_fails_gates', () => {
  const det = deterministicChecks(runNoteCase({}), null, REPORT)
  assert.equal(det.output_ok, false)
  assert.equal(det.schema_ok, false)
  assert.equal(det.grounding_ok, false)
  // pyCheck verdicts are passed through
  const bad = deterministicChecks(runNoteCase({}), note(), REPORT, {
    pyCheck: { schema_ok: true, grounding_ok: false, errors: ['grounding: x'] },
  })
  assert.equal(bad.grounding_ok, false)
  assert.equal(bad.why.grounding_ok, 'grounding: x')
})

test('test_combine_case_pass_requires_all_applicable', () => {
  const det = deterministicChecks(runNoteCase({}), note(), REPORT, { pyCheck: PY_OK })
  assert.equal(combine(det, { must: [true, false], must_not: [true], notes: '' }).case_pass, false)
  const passed = combine(det, { must: [true], must_not: [true], notes: '' })
  assert.equal(passed.case_pass, true)
  assert.equal(passed.must_ok, true)
  // no judge: judge metrics stay null, the deterministic ones decide
  const noJudge = combine(det, null)
  assert.equal(noJudge.must_ok, null)
  assert.equal(noJudge.case_pass, true)
  // all-null -> null
  assert.equal(combine({}, null).case_pass, null)
  assert.equal(combine({ output_ok: null }, { must: [], must_not: [] }).case_pass, null)
})

test('test_judge_skips_model_without_items_and_maps_verdicts', async () => {
  let calls = 0
  const run = async () => {
    calls++
    return JSON.stringify({
      structured_output: { must: [{ pass: true, reason: 'r' }], must_not: [{ pass: false, reason: 'quoted' }], notes: 'n' },
      modelUsage: { 'claude-fable-5-1': {} },
    })
  }
  const empty = await judge(runNoteCase({}), note(), {}, { run })
  assert.deepEqual([empty.must, empty.must_not, calls], [[], [], 0])
  const j = await judge(runNoteCase({ must: ['a'], must_not: ['b'] }), note(), {}, { run })
  assert.deepEqual([j.must, j.must_not, calls], [[true], [false], 1])
  assert.equal(combine({ output_ok: true }, j).must_not_ok, false)
  await assert.rejects(judge(runNoteCase({ must: ['a', 'b'] }), note(), {}, { run }), /expected 2\/0/)
})

test('test_load_cases_prefers_local', () => {
  const dir = mkdtempSync(join(tmpdir(), 'coach-review-cases-'))
  try {
    const example = [{ id: 'ex', kind: 'conversation', pattern: 'A', prompt: 'q?', expect: {} }]
    const local = [{ id: 'real', kind: 'run_note', pattern: 'B', activity_id: 42, date: '2026-01-01', expect: {} }]
    writeFileSync(join(dir, 'cases.example.json'), JSON.stringify(example))
    writeFileSync(join(dir, 'cases.local.json'), JSON.stringify(local))
    const warnings = []
    const warn = (m) => warnings.push(m)
    const a = loadCases(dir, { warn })
    assert.deepEqual(a.cases.map((c) => c.id), ['real'])
    assert.equal(a.synthetic, false)
    assert.equal(warnings.length, 0)
    rmSync(join(dir, 'cases.local.json'))
    const b = loadCases(dir, { warn })
    assert.deepEqual(b.cases.map((c) => c.id), ['ex'])
    assert.equal(b.synthetic, true)
    assert.equal(warnings.length, 1)
    assert.match(warnings[0], /synthetic/)
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
})

test('test_shipped_example_cases_are_valid', () => {
  const { cases } = loadCases(new URL('../../hillclimb/coach-review/', import.meta.url).pathname, { warn: () => {} })
  assert.ok(cases.length >= 2)
  for (const c of cases) assert.equal(caseProblem(c), null, c.id)
  assert.deepEqual([...new Set(cases.map((c) => c.kind))].sort(), ['conversation', 'run_note'])
  assert.match(caseProblem({ id: 'x', kind: 'run_note', pattern: 'A', expect: {} }), /activity_id/)
  assert.match(caseProblem({ id: 'x', kind: 'conversation', pattern: 'Z', prompt: 'q', expect: {} }), /pattern/)
})

test('test_run_note_prompt_comes_from_the_workflow', () => {
  const p = loadRunNotePrompt()({ activityId: 123, activityDate: '2026-01-01', tempDir: '/tmp/coach-review-eval/x' })
  assert.match(p, /get_run_note_inputs\(activity_id=123\)/)
  assert.match(p, /\/tmp\/coach-review-eval\/x\/run_note\.json/)
})

test('test_conversation_probe_is_read_only', () => {
  const names = ['get_run_report', 'export', 'prefetch_activity_context', 'save_symptom', 'ingest_activity', 'reload_server', 'get_run_note_inputs']
  const conv = toolPermissions('conversation', names, '/tmp/x')
  assert.deepEqual(
    conv.allow.filter((t) => t.startsWith('mcp__')).sort(),
    ['mcp__garmin-db__export', 'mcp__garmin-db__get_run_note_inputs', 'mcp__garmin-db__get_run_report', 'mcp__garmin-db__prefetch_activity_context'],
  )
  for (const t of ['mcp__garmin-db__save_symptom', 'mcp__garmin-db__ingest_activity', 'mcp__garmin-db__reload_server', 'Bash', 'Write', 'Edit', 'mcp__github'])
    assert.ok(conv.deny.includes(t), t)
  const rn = toolPermissions('run_note', names, '/tmp/x')
  assert.ok(rn.allow.includes('mcp__garmin-db__get_run_note_inputs'))
  assert.ok(rn.allow.includes('Write(//tmp/x/**)'))
  assert.ok(rn.deny.includes('mcp__garmin-db__export'))
  assert.ok(rn.deny.includes('Bash'))
})

test('test_garmin_tools_reached_true', () => {
  assert.equal(garminToolsReached([{ name: 'Write' }, { name: 'mcp__garmin-db__get_run_note_inputs' }]), true)
})

test('test_garmin_tools_reached_false_when_only_write', () => {
  assert.equal(garminToolsReached([{ name: 'Write' }]), false)
  assert.equal(garminToolsReached([]), false)
  assert.equal(garminToolsReached(undefined), false)
})

test('test_case_env_blocks_on_mcp', () => {
  process.env.CLAUDE_CODE_TEST_MARKER = '1'
  try {
    const env = caseEnv()
    assert.equal(env.MCP_CONNECTION_NONBLOCKING, 'false')
    assert.equal(Object.keys(env).some((k) => k.startsWith('CLAUDE_CODE_')), false)
  } finally {
    delete process.env.CLAUDE_CODE_TEST_MARKER
  }
})
