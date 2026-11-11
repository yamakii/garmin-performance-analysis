// Unit tests for the multi-turn conversation cases of the coach-review eval
// runner (.claude/hillclimb/coach-review/run-eval.mjs, #1566). Synthetic data
// only; the `claude` CLI is stubbed, so no model is called.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { deterministicChecks, judge, judgeUserPrompt, O2_MULTI_TURN } from '../../hillclimb/coach-review/grade.mjs'
import {
  buildTurnArgs,
  mergeTurnTranscripts,
  runSession,
  sumTurnResults,
  toTranscript,
  validateCase,
} from '../../hillclimb/coach-review/run-eval.mjs'

const INCIDENT = { logged: '2026-11-11', source: 'self', triage: 'principle', surface: 'coach' }
const conversation = (extra = {}) => ({
  id: 'q1', kind: 'conversation', pattern: 'C', prompt: '来週の距離は増やせますか？', expect: {}, ...INCIDENT, ...extra,
})

const assistantText = (text) => ({ type: 'assistant', message: { content: [{ type: 'text', text }] } })
const resultEvent = (extra = {}) => ({ type: 'result', result: 'answer', session_id: 'abc', num_turns: 1, total_cost_usd: 0.1,
  usage: { input_tokens: 10, output_tokens: 5 }, modelUsage: { 'claude-opus-5-5': { outputTokens: 5 } }, ...extra })

// ── buildTurnArgs ───────────────────────────────────────────────────────
test('test_build_turn_args_resumes_session', () => {
  const base = ['--model', 'opus', '--output-format', 'stream-json']
  const args = buildTurnArgs(base, 'abc', 'それは過剰では？')
  const i = args.indexOf('--resume')
  assert.ok(i >= 0)
  assert.deepEqual(args.slice(i, i + 4), ['--resume', 'abc', '-p', 'それは過剰では？'])
  for (const a of base) assert.ok(args.includes(a))
  // a resumed turn must itself stay resumable
  assert.equal(buildTurnArgs([...base, '--no-session-persistence'], 'abc', 'x').includes('--no-session-persistence'), false)
  assert.throws(() => buildTurnArgs(base, '', 'x'), /session id/)
})

// ── mergeTurnTranscripts ────────────────────────────────────────────────
test('test_merge_two_turns_keeps_order', () => {
  const t = mergeTurnTranscripts([
    { prompt: 'user1', events: [assistantText('assistant1'), resultEvent()] },
    { prompt: 'user2', events: [assistantText('assistant2'), resultEvent()] },
  ])
  assert.deepEqual(t, [
    { role: 'user', content: 'user1' },
    { role: 'assistant', content: 'assistant1' },
    { role: 'user', content: 'user2' },
    { role: 'assistant', content: 'assistant2' },
  ])
})

test('test_merge_single_turn_matches_old_shape', () => {
  const events = [
    { type: 'assistant', message: { content: [{ type: 'tool_use', id: 't1', name: 'mcp__garmin-db__get_x', input: { a: 1 } }] } },
    { type: 'user', message: { content: [{ type: 'tool_result', tool_use_id: 't1', content: [{ type: 'text', text: 'r' }] }] } },
    assistantText('final'),
    resultEvent(),
  ]
  const meta = { kind: 'conversation', model: 'claude-opus-5-5', effort: 'medium' }
  assert.deepEqual(mergeTurnTranscripts([{ prompt: 'q', events }], meta), toTranscript(events, 'q', meta))
})

// ── case validation ─────────────────────────────────────────────────────
test('test_turns_rejected_on_run_note', () => {
  const kase = { id: 'r1', kind: 'run_note', pattern: 'A', activity_id: 1, date: '2026-01-01', expect: {}, ...INCIDENT, surface: 'run_note', turns: ['x'] }
  assert.match(validateCase(kase), /turns/)
})

test('test_turns_over_three_rejected', () => {
  assert.match(validateCase(conversation({ turns: ['a', 'b', 'c', 'd'] })), /turns/)
  assert.equal(validateCase(conversation({ turns: ['a', 'b', 'c'] })), null)
  assert.match(validateCase(conversation({ turns: [] })), /turns/)
  assert.match(validateCase(conversation({ turns: ['  '] })), /turns/)
})

// ── session runner (stubbed CLI) ────────────────────────────────────────
test('test_run_session_resumes_each_follow_up', async () => {
  const calls = []
  const spawnFn = async (cmd, args) => {
    calls.push(args)
    const n = calls.length
    const out = [assistantText(`a${n}`), resultEvent({ result: `a${n}`, session_id: `s${n}` })].map((e) => JSON.stringify(e)).join('\n')
    return { code: 0, out, err: '' }
  }
  const turns = await runSession(['q1', 'q2', 'q3'], ['--model', 'opus'], { spawnFn, env: {} })
  assert.equal(turns.length, 3)
  assert.deepEqual(calls[0].slice(0, 2), ['-p', 'q1'])
  assert.equal(calls[0].includes('--resume'), false)
  // each follow-up resumes the session id the previous turn reported
  assert.deepEqual(calls[1].slice(0, 4), ['--resume', 's1', '-p', 'q2'])
  assert.deepEqual(calls[2].slice(0, 4), ['--resume', 's2', '-p', 'q3'])
  assert.deepEqual(turns.map((t) => t.result.result), ['a1', 'a2', 'a3'])
})

test('test_run_session_missing_result_is_harness_failure', async () => {
  const spawnFn = async () => ({ code: 1, out: '', err: 'boom' })
  await assert.rejects(runSession(['q'], [], { spawnFn, env: {} }), (e) => e.failure_class === 'harness' && /turn 1/.test(e.message))
})

test('test_sum_turn_results_adds_cost_and_turns', () => {
  const s = sumTurnResults([resultEvent({ num_turns: 3, total_cost_usd: 0.2 }), resultEvent({ num_turns: 2, total_cost_usd: 0.3 })])
  assert.equal(s.num_turns, 5)
  assert.ok(Math.abs(s.cost_usd - 0.5) < 1e-9)
  assert.equal(s.usage.input_tokens, 20)
  assert.equal(s.modelUsage['claude-opus-5-5'].outputTokens, 10)
  assert.equal(sumTurnResults([{}]).cost_usd, null)
})

// ── grading over the exchange ───────────────────────────────────────────
test('test_judge_prompt_labels_every_turn', () => {
  const kase = conversation({ turns: ['それは過剰では？'] })
  const p = judgeUserPrompt(kase, 'final', {}, ['first', 'final'])
  assert.match(p, /TURN 1\n<question>\n来週の距離は増やせますか？\n<\/question>\n<answer>\nfirst\n<\/answer>/)
  assert.match(p, /TURN 2\n<question>\nそれは過剰では？\n<\/question>\n<answer>\nfinal\n<\/answer>/)
  assert.match(p, /whole exchange/)
  assert.ok(p.includes(O2_MULTI_TURN))
  // a single-turn case keeps the old prompt: no turns, no consistency clause
  const single = judgeUserPrompt(conversation(), 'final', {})
  assert.equal(single.includes('TURN 1'), false)
  assert.equal(single.includes(O2_MULTI_TURN), false)
})

test('test_judge_passes_answers_through', async () => {
  let seen = ''
  const run = async (_args, prompt) => {
    seen = prompt
    return JSON.stringify({ structured_output: { must: [], must_not: [], rubric: [], notes: '' } })
  }
  await judge(conversation({ turns: ['x'] }), 'final', {}, { run, answers: ['first', 'final'] })
  assert.match(seen, /<answer>\nfirst\n<\/answer>/)
})

test('test_forbid_regex_covers_every_turn', () => {
  const kase = conversation({ turns: ['x'], expect: { forbid_regex: ['完全に撤回'] } })
  assert.equal(deterministicChecks(kase, '最終回答', null, { answers: ['完全に撤回します', '最終回答'] }).forbid_regex_ok, false)
  assert.equal(deterministicChecks(kase, '最終回答', null, { answers: ['方針は維持', '最終回答'] }).forbid_regex_ok, true)
})
