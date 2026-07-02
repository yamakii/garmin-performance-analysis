// Automated tests for the workflow agent-model gate (run by `node --test`,
// picked up by scripts/check-claude-scripts.sh). Exercises the ACTUAL pure
// functions in scripts/check-workflow-agent-model.mjs (single source of truth).
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { test } from 'node:test'

import {
  stripLiterals,
  findViolations,
  makeDefModel,
} from '../../../scripts/check-workflow-agent-model.mjs'

// defModel(name) returns the declared model value (string), false (def without
// model:), or null (def not found). Helpers below stand in for the real one.
const defOpus = () => 'opus'

// ── findViolations() ──────────────────────────────────────────────────────
test('test_flags_missing_model_and_agenttype', () => {
  const v = findViolations("agent(p, { label:'x' })", defOpus)
  assert.equal(v.length, 1)
})

test('test_passes_explicit_model', () => {
  const v = findViolations("agent(p, { model:'haiku' })", defOpus)
  assert.equal(v.length, 0)
})

test('test_passes_agenttype_with_model_def', () => {
  const v = findViolations("agent(p, { agentType:'unified-section-analyst' })", defOpus)
  assert.equal(v.length, 0)
})

test('test_flags_agenttype_without_model_def', () => {
  const v = findViolations("agent(p, { agentType:'foo' })", () => false)
  assert.equal(v.length, 1)
})

test('test_flags_agenttype_missing_def', () => {
  const v = findViolations("agent(p, { agentType:'ghost' })", () => null)
  assert.equal(v.length, 1)
})

test('test_dynamic_agenttype_passes', () => {
  const v = findViolations("agent(p, { agentType: k ? 'a' : 'b' })", () => false)
  assert.equal(v.length, 0)
})

test('test_ignores_model_in_prompt_text', () => {
  const v = findViolations("agent(`... model: opus ...`, { label:'x' })", defOpus)
  assert.equal(v.length, 1)
})

// ── Allowlist enforcement (Issue #723: cap at opus, drop inherit) ──────────
test('callsite model literal opus passes', () => {
  const v = findViolations("agent('p', { model: 'opus' })", defOpus)
  assert.equal(v.length, 0)
})

test('callsite model literal outside allowlist fails', () => {
  const v = findViolations("agent('p', { model: 'fable' })", defOpus)
  assert.equal(v.length, 1)
  assert.match(v[0].reason, /allowlist/)
})

test('def model inherit is a violation', () => {
  const v = findViolations("agent('p', { agentType: 'developer' })", () => 'inherit')
  assert.equal(v.length, 1)
  assert.match(v[0].reason, /inherit/)
})

test('def model opus passes', () => {
  const v = findViolations("agent('p', { agentType: 'developer' })", () => 'opus')
  assert.equal(v.length, 0)
})

test('dynamic model expression passes', () => {
  const v = findViolations("agent('p', { model: cond ? 'haiku' : 'sonnet' })", defOpus)
  assert.equal(v.length, 0)
})

test('def model outside allowlist fails', () => {
  const v = findViolations("agent('p', { agentType: 'developer' })", () => 'fable')
  assert.equal(v.length, 1)
  assert.match(v[0].reason, /allowlist/)
})

// ── stripLiterals() ───────────────────────────────────────────────────────
test('test_strip_preserves_length', () => {
  const src = 'const p = `a\nb ${x} c`\n// note {z}\nconst q = "d{e}f"\n'
  const out = stripLiterals(src)
  assert.equal(out.length, src.length)
  assert.equal((out.match(/\n/g) || []).length, (src.match(/\n/g) || []).length)
})

test('test_strip_blanks_string_braces', () => {
  const out = stripLiterals('const s = "a{b}c"')
  assert.ok(!out.includes('{'), 'string brace must not survive as structure')
  assert.ok(!out.includes('}'), 'string brace must not survive as structure')
})

// ── Integration: the repo's real workflow files pass after the fix ─────────
test('test_repo_workflows_pass_after_fix', () => {
  const agentsDir = fileURLToPath(new URL('../../agents/', import.meta.url))
  const defModel = makeDefModel(agentsDir)
  for (const name of ['analyze-activity.js', 'implement-tier.js']) {
    const src = readFileSync(new URL(`../${name}`, import.meta.url), 'utf8')
    const v = findViolations(src, defModel)
    assert.equal(v.length, 0, `${name} has violations: ${JSON.stringify(v)}`)
  }
})
