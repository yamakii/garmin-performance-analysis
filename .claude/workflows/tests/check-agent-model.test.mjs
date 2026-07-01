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
  makeDefHasModel,
} from '../../../scripts/check-workflow-agent-model.mjs'

// ── findViolations() ──────────────────────────────────────────────────────
test('test_flags_missing_model_and_agenttype', () => {
  const v = findViolations("agent(p, { label:'x' })", () => true)
  assert.equal(v.length, 1)
})

test('test_passes_explicit_model', () => {
  const v = findViolations("agent(p, { model:'haiku' })", () => true)
  assert.equal(v.length, 0)
})

test('test_passes_agenttype_with_model_def', () => {
  const v = findViolations("agent(p, { agentType:'unified-section-analyst' })", () => true)
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
  const v = findViolations("agent(`... model: opus ...`, { label:'x' })", () => true)
  assert.equal(v.length, 1)
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
  const defHasModel = makeDefHasModel(agentsDir)
  for (const name of ['analyze-activity.js', 'implement-tier.js']) {
    const src = readFileSync(new URL(`../${name}`, import.meta.url), 'utf8')
    const v = findViolations(src, defHasModel)
    assert.equal(v.length, 0, `${name} has violations: ${JSON.stringify(v)}`)
  }
})
