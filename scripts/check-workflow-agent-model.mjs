#!/usr/bin/env node
// Gate: every agent() call in .claude/workflows/*.js must resolve a model, so
// no agent silently inherits the (usually Opus) session model — a cost and
// non-determinism trap (e.g. analyze-activity fetch / merge).
//
// A call resolves a model if EITHER:
//   1. it passes an explicit `model:` option (any value), OR
//   2. it passes `agentType:` whose def (.claude/agents/<name>.md) frontmatter
//      declares a `model:` line (`model: inherit` counts — it is an explicit
//      opt-in). A dynamic agentType (ternary/variable, not statically
//      resolvable) is allowed: we can't inspect the branch target, so we trust
//      the author (the runtime def is expected to declare model).
//
// This module exports pure functions (unit-tested via node --test) plus a CLI
// `main` that scans the repo and exits 1 on any violation.
//
// See .claude/rules/dev/workflow-model-gate.md for the rule.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

// Blank out the *contents* of string literals, template literals, and comments
// while preserving overall length and newline positions. Template `${...}`
// expressions are kept as code (they can contain nested objects/strings). This
// lets brace/comma scanning see real code structure without being polluted by
// braces/commas/colons that live inside strings or comments (e.g. a prompt that
// literally contains "model: opus").
export function stripLiterals(src) {
  const out = src.split('')
  const n = src.length
  const blank = (idx) => {
    const ch = src[idx]
    if (ch !== '\n' && ch !== '\r') out[idx] = ' '
  }
  // Stack of frames. mode: code | line | block | sq | dq | tpl.
  // A code frame tracks its own brace depth so a `}` closing a template
  // expression (`${ ... }`) pops back to the enclosing template string.
  const stack = [{ mode: 'code', brace: 0 }]
  let i = 0
  while (i < n) {
    const f = stack[stack.length - 1]
    const c = src[i]
    const c2 = src[i + 1]
    if (f.mode === 'code') {
      if (c === '/' && c2 === '/') {
        blank(i)
        blank(i + 1)
        stack.push({ mode: 'line' })
        i += 2
        continue
      }
      if (c === '/' && c2 === '*') {
        blank(i)
        blank(i + 1)
        stack.push({ mode: 'block' })
        i += 2
        continue
      }
      if (c === "'") {
        stack.push({ mode: 'sq' })
        i += 1
        continue
      }
      if (c === '"') {
        stack.push({ mode: 'dq' })
        i += 1
        continue
      }
      if (c === '`') {
        stack.push({ mode: 'tpl' })
        i += 1
        continue
      }
      if (c === '{') {
        f.brace += 1
        i += 1
        continue
      }
      if (c === '}') {
        if (f.brace === 0 && stack.length > 1) {
          // closes a template expression → back to the template string
          stack.pop()
          i += 1
          continue
        }
        if (f.brace > 0) f.brace -= 1
        i += 1
        continue
      }
      i += 1
      continue
    }
    if (f.mode === 'line') {
      if (c === '\n') {
        stack.pop()
        i += 1
        continue
      }
      blank(i)
      i += 1
      continue
    }
    if (f.mode === 'block') {
      if (c === '*' && c2 === '/') {
        blank(i)
        blank(i + 1)
        stack.pop()
        i += 2
        continue
      }
      blank(i)
      i += 1
      continue
    }
    if (f.mode === 'sq' || f.mode === 'dq') {
      const q = f.mode === 'sq' ? "'" : '"'
      if (c === '\\') {
        blank(i)
        blank(i + 1)
        i += 2
        continue
      }
      if (c === q) {
        stack.pop()
        i += 1
        continue
      }
      blank(i)
      i += 1
      continue
    }
    if (f.mode === 'tpl') {
      if (c === '\\') {
        blank(i)
        blank(i + 1)
        i += 2
        continue
      }
      if (c === '`') {
        stack.pop()
        i += 1
        continue
      }
      if (c === '$' && c2 === '{') {
        // enter code for the expression; keep `${` as code
        stack.push({ mode: 'code', brace: 0 })
        i += 2
        continue
      }
      blank(i)
      i += 1
      continue
    }
    i += 1
  }
  return out.join('')
}

// Given the raw text of an object literal (including the outer braces), return
// its top-level entries as { key, valueStart } using the stripped copy for
// structure and the raw copy for the key text.
function scanTopLevelEntries(optsRaw) {
  const s = stripLiterals(optsRaw)
  const entries = []
  let i = s.indexOf('{')
  if (i < 0) return entries
  i += 1
  let depth = 0
  let expectKey = true
  while (i < s.length) {
    const c = s[i]
    if (depth === 0 && c === '}') break
    if (c === '{' || c === '[' || c === '(') {
      depth += 1
      i += 1
      continue
    }
    if (c === '}' || c === ']' || c === ')') {
      depth -= 1
      i += 1
      continue
    }
    if (depth === 0) {
      if (c === ',') {
        expectKey = true
        i += 1
        continue
      }
      if (expectKey && /\S/.test(c)) {
        // read a key token until a top-level ':' , ',' , '}' or a nesting open
        let j = i
        while (
          j < s.length &&
          s[j] !== ':' &&
          s[j] !== ',' &&
          s[j] !== '}' &&
          s[j] !== '{' &&
          s[j] !== '[' &&
          s[j] !== '('
        ) {
          j += 1
        }
        if (s[j] === ':') {
          entries.push({ key: optsRaw.slice(i, j).trim(), valueStart: j + 1 })
          expectKey = false
          i = j + 1
          continue
        }
        // shorthand / spread / method — no colon; skip this token
        expectKey = false
        i = j
        continue
      }
    }
    i += 1
  }
  return entries
}

// Top-level key names of an object literal body (quotes stripped from string
// keys). optsRaw includes the outer braces.
export function optionKeys(optsRaw) {
  if (!optsRaw) return []
  return scanTopLevelEntries(optsRaw).map((e) => e.key.replace(/^['"`]|['"`]$/g, ''))
}

// If `agentType`'s value is a plain string literal, return its name; otherwise
// (dynamic: ternary / variable / expression, or absent) return null.
export function agentTypeLiteral(optsRaw) {
  if (!optsRaw) return null
  const entries = scanTopLevelEntries(optsRaw)
  const at = entries.find((e) => e.key.replace(/^['"`]|['"`]$/g, '') === 'agentType')
  if (!at) return null
  const s = stripLiterals(optsRaw)
  let i = at.valueStart
  let depth = 0
  let end = s.length
  while (i < s.length) {
    const c = s[i]
    if (c === '{' || c === '[' || c === '(') depth += 1
    else if (c === '}' || c === ']' || c === ')') {
      if (depth === 0) {
        end = i
        break
      }
      depth -= 1
    } else if (c === ',' && depth === 0) {
      end = i
      break
    }
    i += 1
  }
  const rawVal = optsRaw.slice(at.valueStart, end).trim()
  const m = rawVal.match(/^(['"`])([A-Za-z0-9_-]+)\1$/)
  return m ? m[2] : null
}

// Detect each agent(...) call and return the raw text of its last top-level
// object-literal argument (or null if there is none).
export function findAgentCalls(src) {
  const s = stripLiterals(src)
  const calls = []
  const re = /(?<![\w.])agent\s*\(/g
  let m
  while ((m = re.exec(s))) {
    const callIndex = m.index
    let i = m.index + m[0].length // just past '('
    let depth = 0
    let argStart = i
    const args = []
    while (i < s.length) {
      const c = s[i]
      if (c === '(' || c === '{' || c === '[') depth += 1
      else if (c === ')') {
        if (depth === 0) {
          args.push({ start: argStart, end: i })
          break
        }
        depth -= 1
      } else if (c === '}' || c === ']') depth -= 1
      else if (c === ',' && depth === 0) {
        args.push({ start: argStart, end: i })
        argStart = i + 1
      }
      i += 1
    }
    let optsRaw = null
    for (let a = args.length - 1; a >= 0; a -= 1) {
      if (s.slice(args[a].start, args[a].end).trim().startsWith('{')) {
        const rawSeg = src.slice(args[a].start, args[a].end)
        const lb = rawSeg.indexOf('{')
        const rb = rawSeg.lastIndexOf('}')
        optsRaw = rawSeg.slice(lb, rb + 1)
        break
      }
    }
    calls.push({ index: callIndex, optsRaw })
  }
  return calls
}

// Return the list of gate violations. defHasModel(name) returns true (model
// declared), false (def exists without model), or null (def not found).
export function findViolations(src, defHasModel) {
  const violations = []
  const lineOf = (idx) => src.slice(0, idx).split('\n').length
  for (const call of findAgentCalls(src)) {
    const line = lineOf(call.index)
    if (!call.optsRaw) {
      violations.push({ line, reason: 'agent() call has no options object (model unresolvable)' })
      continue
    }
    const keys = optionKeys(call.optsRaw)
    if (keys.includes('model')) continue
    if (keys.includes('agentType')) {
      const name = agentTypeLiteral(call.optsRaw)
      if (name === null) continue // dynamic agentType — trust the author
      const has = defHasModel(name)
      if (has === true) continue
      if (has === false)
        violations.push({ line, reason: `agentType '${name}' def declares no model:` })
      else violations.push({ line, reason: `agentType '${name}' def not found` })
      continue
    }
    violations.push({ line, reason: 'agent() call has neither model: nor agentType:' })
  }
  return violations
}

// Build a defHasModel predicate backed by .claude/agents/<name>.md frontmatter.
export function makeDefHasModel(agentsDir) {
  return (name) => {
    const file = path.join(agentsDir, `${name}.md`)
    if (!fs.existsSync(file)) return null
    const txt = fs.readFileSync(file, 'utf8')
    const fm = txt.match(/^---\n([\s\S]*?)\n---/)
    const body = fm ? fm[1] : txt
    return /^model:\s*\S/m.test(body)
  }
}

function main() {
  const here = path.dirname(fileURLToPath(import.meta.url))
  const root = path.resolve(here, '..')
  const wfDir = path.join(root, '.claude', 'workflows')
  const agentsDir = path.join(root, '.claude', 'agents')
  const defHasModel = makeDefHasModel(agentsDir)

  if (!fs.existsSync(wfDir)) {
    console.log('check-workflow-agent-model: no .claude/workflows dir — nothing to check')
    return 0
  }
  const files = fs
    .readdirSync(wfDir)
    .filter((f) => f.endsWith('.js'))
    .map((f) => path.join(wfDir, f))

  let total = 0
  for (const file of files) {
    const src = fs.readFileSync(file, 'utf8')
    const violations = findViolations(src, defHasModel)
    for (const v of violations) {
      console.error(
        `FAIL (agent model gate): ${path.relative(root, file)}:${v.line} — ${v.reason}`,
      )
    }
    total += violations.length
  }

  if (total > 0) {
    console.error(
      `check-workflow-agent-model: ${total} violation(s). Every agent() must set model: ` +
        `or an agentType whose def declares model:. See .claude/rules/dev/workflow-model-gate.md`,
    )
    return 1
  }
  console.log('check-workflow-agent-model: all agent() calls resolve a model')
  return 0
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  process.exit(main())
}
