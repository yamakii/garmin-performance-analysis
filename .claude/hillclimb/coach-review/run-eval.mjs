#!/usr/bin/env node
// coach-review eval runner (same shape as .claude/hillclimb/trend-narration/run-eval.mjs).
//
// Two case kinds (cases.schema.json):
//   - run_note:     runs the run-note-analyst headless (`claude -p --agent run-note-analyst`)
//                   with the workflow's own buildRunNotePrompt (from the `// >>> testable`
//                   block of .claude/workflows/analyze-activity.js), writes run_note.json to a
//                   scratch dir, and grades it. Nothing is merged: the merge gates run through
//                   the read-only garmin_mcp.scripts.check_run_note CLI.
//   - conversation: a single-turn probe `claude -p "<question>"` in the repo root, so
//                   CLAUDE.md and the rules load, with READ-ONLY tools only (Read/Glob/Grep and
//                   the garmin-db get_* / export / prefetch_* tools). The final answer is graded.
//
// The harness never writes to DuckDB. Run from the repo root:
//
//   node .claude/hillclimb/coach-review/run-eval.mjs \
//     --flow .claude/hillclimb/coach-review --variant baseline --model opus --effort medium
//
// Cases come from cases.local.json (gitignored, real cases) when present, else from the
// synthetic cases.example.json with a warning. Spends Max usage: ask before a full run.
//
// Structural properties (as in trend-narration):
//   - parameterized by --variant / --model / --reps; rep-aware filenames + resume
//   - reads _state.json, never writes it, except --approve-harness recording `harness_sha`
//   - refuses to run when the harness (this file + _state.json.harness_paths) changed since
//     the sha a human last approved
//   - rows land as cases complete; failed attempts go to errors.jsonl with a failure class
//   - jittered exponential backoff on transient errors; hard per-case wall-clock ceiling
//   - served-model family check on the main model of the headless run

import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { appendFileSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { cleanEnv, combine, deterministicChecks, judge } from './grade.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(HERE, '../../..')
const WORKFLOW = join(REPO, '.claude/workflows/analyze-activity.js')
const TOOLS_SNAPSHOT = join(REPO, 'packages/garmin-mcp-server/tests/snapshots/all_tools_golden.json')
const SERVER_DIR = join(REPO, 'packages/garmin-mcp-server')
const SCRATCH = join(tmpdir(), 'coach-review-eval')

// ── cases ───────────────────────────────────────────────────────────────
// cases.local.json (gitignored) holds the real cases; the repo carries only the
// synthetic example. Results from the example are not a measurement of anything.
export function loadCases(flowDir, { warn = (m) => console.error(m) } = {}) {
  const local = join(flowDir, 'cases.local.json')
  const example = join(flowDir, 'cases.example.json')
  const synthetic = !existsSync(local)
  const path = synthetic ? example : local
  if (synthetic)
    warn(`warning: ${relative(process.cwd(), local) || local} not found - using the synthetic ${relative(process.cwd(), example) || example}; results are synthetic and measure nothing`)
  const cases = JSON.parse(readFileSync(path, 'utf8'))
  if (!Array.isArray(cases)) throw new Error(`${path}: expected an array of cases`)
  for (const c of cases) {
    const problem = caseProblem(c)
    if (problem) throw new Error(`${path}: case ${JSON.stringify(c?.id ?? null)}: ${problem}`)
  }
  return { cases, path, synthetic }
}

// The subset of cases.schema.json the runner relies on (no schema library here).
export function caseProblem(c) {
  if (!c || typeof c !== 'object') return 'not an object'
  if (typeof c.id !== 'string' || !/^[A-Za-z0-9_.-]+$/.test(c.id)) return 'id must be a path-safe string'
  if (!['run_note', 'conversation'].includes(c.kind)) return `unknown kind ${JSON.stringify(c.kind)}`
  if (!['A', 'B', 'C', 'D', 'E'].includes(c.pattern)) return `pattern must be one of A-E`
  if (!c.expect || typeof c.expect !== 'object') return 'expect is required'
  for (const k of ['must', 'must_not', 'forbid_regex', 'forbid_growth_point_moment_kinds', 'required_evidence_prefixes'])
    if (c.expect[k] != null && !(Array.isArray(c.expect[k]) && c.expect[k].every((s) => typeof s === 'string')))
      return `expect.${k} must be an array of strings`
  for (const p of c.expect.forbid_regex ?? []) {
    try { new RegExp(p, 'u') } catch (e) { return `expect.forbid_regex ${JSON.stringify(p)}: ${e.message}` }
  }
  if (c.kind === 'run_note') {
    if (!Number.isInteger(c.activity_id)) return 'run_note cases need an integer activity_id'
    if (typeof c.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(c.date)) return 'run_note cases need date YYYY-MM-DD'
  } else if (typeof c.prompt !== 'string' || !c.prompt.trim()) return 'conversation cases need a prompt'
  return null
}

// ── tool permissions ────────────────────────────────────────────────────
// Read-only garmin-db tools: get_*, export, prefetch_* (get_server_info is harmless).
// The full list comes from the tool registry snapshot so a new write tool is
// denied by default instead of slipping through.
const isReadOnlyTool = (name) => name.startsWith('get_') || name === 'export' || name.startsWith('prefetch_')
const RUN_NOTE_TOOLS = ['get_run_note_inputs', 'get_analysis_contract', 'validate_section_json']
const ALWAYS_DENY = ['Bash', 'NotebookEdit', 'Agent', 'Task', 'Workflow', 'WebFetch', 'WebSearch', 'mcp__github', 'mcp__serena']
// File-editing tools are denied outright for a probe. A run_note run keeps them
// out of the deny list (a bare Edit deny can cover every file-editing tool and
// would block the one Write the analyst needs); the agent def grants Write only,
// and the allow rule scopes it to the scratch dir.
const CONVERSATION_DENY = ['Write', 'Edit']

function garminTools() {
  const names = JSON.parse(readFileSync(TOOLS_SNAPSHOT, 'utf8')).map((t) => t?.name).filter((n) => typeof n === 'string')
  if (!names.length) throw new Error(`no tool names in ${TOOLS_SNAPSHOT}`)
  return names
}
const mcp = (n) => `mcp__garmin-db__${n}`

export function toolPermissions(kind, names = garminTools(), scratchDir = SCRATCH) {
  const allowedGarmin = kind === 'run_note' ? RUN_NOTE_TOOLS : names.filter(isReadOnlyTool)
  const allow = allowedGarmin.map(mcp)
  if (kind === 'run_note') allow.push(`Write(/${scratchDir}/**)`)
  else allow.push('Read', 'Glob', 'Grep', 'ToolSearch')
  const deny = [...ALWAYS_DENY, ...names.filter((n) => !allowedGarmin.includes(n)).map(mcp)]
  if (kind === 'conversation') deny.push(...CONVERSATION_DENY)
  return { allow, deny }
}

// ── the app under test ──────────────────────────────────────────────────
// The run_note prompt is the workflow's own buildRunNotePrompt (single source of truth).
export function loadRunNotePrompt() {
  const src = readFileSync(WORKFLOW, 'utf8')
  const m = src.match(/\/\/ >>> testable\n([\s\S]*?)\n\s*\/\/ <<< testable/)
  if (!m) throw new Error('testable block markers not found in analyze-activity.js')
  // eslint-disable-next-line no-new-func
  return new Function(`${m[1]}\nreturn buildRunNotePrompt`)()
}

function mainModel(modelUsage) {
  const e = Object.entries(modelUsage ?? {})
  e.sort((a, b) => (b[1].outputTokens ?? 0) - (a[1].outputTokens ?? 0))
  return e[0]?.[0] ?? null
}

const clip = (s, n = 6000) => (s.length > n ? `${s.slice(0, n)}\n… [${s.length - n} chars clipped in trace]` : s)
const toolResultText = (b) => (Array.isArray(b.content) ? b.content.map((x) => x.text ?? '').join('\n') : String(b.content ?? ''))

function toTranscript(events, prompt, meta) {
  const t = [{ role: 'system', content: `Claude Code headless (cwd=repo root). kind=${meta.kind} model=${meta.model} effort=${meta.effort ?? '(settings)'}` },
             { role: 'user', content: prompt }]
  for (const ev of events) {
    const blocks = ev.message?.content
    if (!Array.isArray(blocks)) continue
    for (const b of blocks) {
      if (ev.type === 'assistant' && b.type === 'text' && b.text.trim()) t.push({ role: 'assistant', content: b.text })
      else if (ev.type === 'assistant' && b.type === 'tool_use') t.push({ role: 'tool_call', name: b.name, content: JSON.stringify(b.input, null, 2) })
      else if (ev.type === 'user' && b.type === 'tool_result') t.push({ role: 'tool_result', content: clip(toolResultText(b)) })
    }
  }
  return t
}

// Tool calls and their results, paired, for the judge's CONTEXT and for
// recovering the run report the analyst actually read.
function toolExchanges(events) {
  const calls = new Map()
  const out = []
  for (const ev of events) {
    for (const b of Array.isArray(ev.message?.content) ? ev.message.content : []) {
      if (ev.type === 'assistant' && b.type === 'tool_use') calls.set(b.id, { name: b.name, input: b.input })
      else if (ev.type === 'user' && b.type === 'tool_result') {
        const c = calls.get(b.tool_use_id)
        out.push({ name: c?.name ?? null, input: c?.input ?? null, result: toolResultText(b), is_error: b.is_error === true })
      }
    }
  }
  return out
}

function parseJsonLoose(s) {
  try { return JSON.parse(s) } catch {}
  const i = s.indexOf('{')
  const j = s.lastIndexOf('}')
  if (i >= 0 && j > i) try { return JSON.parse(s.slice(i, j + 1)) } catch {}
  return null
}

function spawnCollect(cmd, args, { cwd, timeoutMs, env = cleanEnv() }) {
  return new Promise((res, rej) => {
    const p = spawn(cmd, args, { cwd, env, stdio: ['ignore', 'pipe', 'pipe'] })
    let out = '', err = ''
    const timer = setTimeout(() => p.kill('SIGTERM'), timeoutMs)
    p.stdout.on('data', (d) => (out += d))
    p.stderr.on('data', (d) => (err += d))
    p.on('close', (code) => { clearTimeout(timer); res({ code, out, err }) })
    p.on('error', (e) => { clearTimeout(timer); rej(e) })
  })
}

// Read-only fallback when the transcript does not carry the report (e.g. the
// analyst never called get_run_note_inputs): the report the page would render.
async function fetchReport(activityId) {
  const code = `import json; from garmin_mcp.database.db_reader import GarminDBReader; print(json.dumps(GarminDBReader().get_run_report(${Number(activityId)}), default=str, ensure_ascii=False))`
  const { out } = await spawnCollect('uv', ['run', '--directory', SERVER_DIR, 'python', '-c', code], { cwd: REPO, timeoutMs: 300_000 })
  return parseJsonLoose(out.trim().split('\n').at(-1) ?? '')
}

// The merge gates, without the merge (garmin_mcp.scripts.check_run_note).
export async function checkRunNoteCli(reportPath, notePath) {
  const { out, err } = await spawnCollect(
    'uv', ['run', '--directory', SERVER_DIR, 'python', '-m', 'garmin_mcp.scripts.check_run_note', '--report', reportPath, '--note', notePath],
    { cwd: REPO, timeoutMs: 300_000 },
  )
  const r = parseJsonLoose(out.trim().split('\n').at(-1) ?? '')
  if (!r || typeof r.schema_ok !== 'boolean') {
    const e = new Error(`check_run_note produced no verdict: ${(err || out).slice(0, 300)}`)
    e.failure_class = 'harness'
    throw e
  }
  return r
}

async function runCase(input, ctx) {
  const stem = `${input.id}_rep${ctx.rep}`
  const tempDir = join(SCRATCH, ctx.variant, stem)
  rmSync(tempDir, { recursive: true, force: true })
  mkdirSync(tempDir, { recursive: true })
  const perms = toolPermissions(input.kind)
  const prompt = input.kind === 'run_note'
    ? ctx.runNotePrompt({ activityId: input.activity_id, activityDate: input.date, tempDir })
    : input.prompt
  const args = ['-p', prompt, '--model', ctx.model, '--output-format', 'stream-json', '--verbose',
    '--permission-mode', 'dontAsk', '--no-session-persistence',
    '--allowedTools', ...perms.allow, '--disallowedTools', ...perms.deny]
  if (input.kind === 'run_note') args.push('--agent', 'run-note-analyst', '--add-dir', tempDir)
  if (ctx.effort) args.push('--effort', ctx.effort)
  const { code, out, err } = await spawnCollect('claude', args, { cwd: REPO, timeoutMs: ctx.timeoutS > 0 ? ctx.timeoutS * 1000 : 2147483647 })
  const events = out.split('\n').filter(Boolean).flatMap((l) => { try { return [JSON.parse(l)] } catch { return [] } })
  const result = events.find((e) => e.type === 'result')
  if (!result) {
    const e = new Error(`claude produced no result event (exit ${code}): ${err.slice(0, 300)}`)
    e.failure_class = 'harness'
    throw e
  }
  const model = mainModel(result.modelUsage)
  const family = ctx.model.replace(/^claude-/, '').split('-')[0]
  if (!model || !model.includes(family)) {
    const e = new Error(`served model ${model} is not a ${family} model`)
    e.failure_class = 'serving_substitution'
    throw e
  }
  const u = result.usage ?? {}
  const usage = { input_tokens: u.input_tokens ?? 0, output_tokens: u.output_tokens ?? 0,
    cache_read_input_tokens: u.cache_read_input_tokens ?? 0, cache_creation_input_tokens: u.cache_creation_input_tokens ?? 0 }
  const exchanges = toolExchanges(events)
  const outDir = join(ctx.flow, ctx.variant, 'out')
  mkdirSync(outDir, { recursive: true })

  let output = null, report = null, pyCheck = null, judgeContext
  if (input.kind === 'run_note') {
    try { output = JSON.parse(readFileSync(join(tempDir, 'run_note.json'), 'utf8')) } catch {}
    // The report the analyst read; the live report only when the call is missing.
    const inputs = exchanges.find((x) => x.name === mcp('get_run_note_inputs') && !x.is_error)
    const parsed = inputs ? parseJsonLoose(inputs.result) : null
    report = parsed?.report ?? null
    const reportSource = report ? 'transcript' : 'live'
    if (!report) report = await fetchReport(input.activity_id)
    if (!report || report.error) {
      const e = new Error(`no run report for activity ${input.activity_id}`)
      e.failure_class = 'harness'
      throw Object.assign(e, { usage, model })
    }
    const reportPath = join(outDir, `${stem}.report.json`)
    writeFileSync(reportPath, JSON.stringify(report))
    if (output) {
      const notePath = join(outDir, `${stem}.run_note.json`)
      writeFileSync(notePath, JSON.stringify(output, null, 2))
      pyCheck = await checkRunNoteCli(reportPath, notePath)
    }
    judgeContext = { report, context: parsed?.context ?? null, report_source: reportSource }
  } else {
    output = typeof result.result === 'string' ? result.result : null
    if (output != null) writeFileSync(join(outDir, `${stem}.answer.md`), output)
    judgeContext = { tool_results: exchanges.map((x) => ({ tool: x.name, input: x.input, result: clip(x.result, 3000) })) }
  }
  writeFileSync(join(outDir, `${stem}.judge_context.json`), JSON.stringify(judgeContext))
  writeFileSync(join(outDir, `${stem}.pycheck.json`), JSON.stringify(pyCheck))
  const lastAssistant = [...events].reverse().find((e) => e.type === 'assistant')
  return {
    output, report, pyCheck, judgeContext, model, usage, prompt,
    transcript: toTranscript(events, prompt, { kind: input.kind, model, effort: ctx.effort }),
    tools_used: [...new Set(exchanges.map((x) => x.name).filter(Boolean))],
    stop_reason: lastAssistant?.message?.stop_reason ?? result.subtype,
    cost_usd: result.total_cost_usd ?? null,
    num_turns: result.num_turns ?? null,
  }
}

async function gradeCase(input, run, ctx) {
  const det = deterministicChecks(input, run.output, run.report, { pyCheck: run.pyCheck })
  const j = ctx.noJudge ? null : await judge(input, run.output, run.judgeContext)
  const { explanation, ...grade } = combine(det, j)
  return { grade, explanation, judge_model: j?.judge_model, judge_usage: j?.judge_usage, judge_cost_usd: j?.judge_cost_usd ?? null }
}

// ── harness (you usually won't need to touch below this line) ───────────

function parseArgs(argv) {
  const a = { flow: '.claude/hillclimb/coach-review', variant: 'baseline', model: undefined, effort: undefined,
              noJudge: false, only: [], reps: 1, concurrency: 2, timeoutS: 900, approveHarness: false }
  const val = (i) => { if (argv[i] === undefined) { console.error(`missing value for ${argv[i - 1]}`); usage(); process.exit(2) } return argv[i] }
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i]
    if (k === '--flow') a.flow = val(++i)
    else if (k === '--variant') a.variant = val(++i)
    else if (k === '--model') a.model = val(++i)
    else if (k === '--reps') a.reps = +val(++i)
    else if (k === '--concurrency') a.concurrency = +val(++i)
    else if (k === '--timeout-s') a.timeoutS = +val(++i)
    else if (k === '--approve-harness') a.approveHarness = true
    else if (k === '--effort') a.effort = val(++i)
    else if (k === '--no-judge') a.noJudge = true
    else if (k === '--only') a.only = val(++i).split(',').filter(Boolean)
    else if (k === '-h' || k === '--help') { usage(); process.exit(0) }
    else { console.error(`unknown argument: ${k}`); usage(); process.exit(2) }
  }
  if (!/^(baseline|v[1-9]\d*)$/.test(a.variant)) { console.error(`--variant must be 'baseline' or 'v<N>', got '${a.variant}'`); usage(); process.exit(2) }
  if (!a.model) { console.error('--model is required (sonnet | opus | a full model id)'); usage(); process.exit(2) }
  if (a.effort && !['low', 'medium', 'high', 'xhigh', 'max'].includes(a.effort)) { usage(); process.exit(2) }
  if (!Number.isFinite(a.timeoutS) || a.timeoutS < 0 || a.timeoutS * 1000 > 2147483647
      || !Number.isInteger(a.reps) || a.reps < 1 || !Number.isInteger(a.concurrency) || a.concurrency < 1) { usage(); process.exit(2) }
  return a
}
function usage() {
  console.error('usage: node run-eval.mjs --flow DIR --variant ID --model ID [--effort LEVEL] [--no-judge] [--only id,id] [--reps N] [--concurrency N] [--timeout-s N (0 = no ceiling)] [--approve-harness]')
}

// Harness integrity gate (see trend-narration/run-eval.mjs for the rationale):
// sha256 over this file plus `_state.json.harness_paths`; refuse on mismatch
// unless a human passes --approve-harness, which records the new sha.
function checkHarness(statePath, st, approve) {
  const self = fileURLToPath(import.meta.url)
  const listed = Array.isArray(st.harness_paths) ? st.harness_paths.map(String) : []
  const paths = [...new Set([self, ...listed.map((p) => resolve(p))])].sort()
  const h = createHash('sha256')
  const hashed = []
  for (const p of paths) {
    let buf
    try { buf = readFileSync(p) } catch (e) {
      if (p === self) throw e
      console.error(`note: harness path '${relative(process.cwd(), p)}' not readable (${e?.code || 'error'}) - skipped`)
      continue
    }
    h.update(relative(process.cwd(), p)).update('\0').update(buf).update('\0')
    hashed.push(relative(process.cwd(), p))
  }
  const sha = h.digest('hex')
  if (st.harness_sha === sha) return
  if (approve) {
    st.harness_sha = sha
    writeFileSync(statePath, JSON.stringify(st, null, 2) + '\n')
    console.error(`harness approved: sha256 ${sha.slice(0, 12)} over ${hashed.length} file(s) recorded in ${statePath}`)
    return
  }
  if (st.harness_sha == null) {
    console.error(`no approved harness sha in ${statePath} (computed ${sha.slice(0, 12)} over: ${hashed.join(', ')}).`)
    console.error('Review the harness, then run once with --approve-harness to record it.')
  } else {
    console.error(`harness changed since last approved run (files: ${hashed.join(', ')}); approved ${String(st.harness_sha).slice(0, 12)}, now ${sha.slice(0, 12)}.`)
    console.error('Re-run with --approve-harness after reviewing the diff.')
  }
  process.exit(2)
}

async function withBackoff(fn, retry, deadline = Infinity, tries = 5) {
  for (let attempt = 0; ; attempt++) {
    if (Date.now() >= deadline) { const e = new Error('wall-clock ceiling exceeded before attempt'); e.failure_class = 'timeout'; throw e }
    try { return await fn() } catch (e) {
      const status = e?.status ?? e?.response?.status
      const transient = status === 429 || status === 529 || (status >= 500 && status < 600) || /overloaded|rate.?limit/i.test(String(e?.message ?? ''))
      if (!transient || attempt >= tries - 1) throw e
      const delay = Math.min(60_000, 1000 * 2 ** attempt) * (0.5 + Math.random())
      if (Date.now() + delay >= deadline) throw e
      retry.count++
      await new Promise((r) => setTimeout(r, delay))
    }
  }
}

function withTimeout(promise, seconds, label) {
  if (!(seconds > 0)) return promise
  let timer
  const ceiling = new Promise((_, reject) => {
    timer = setTimeout(() => { const e = new Error(`${label}: exceeded ${seconds}s wall-clock ceiling`); e.failure_class = 'timeout'; reject(e) }, seconds * 1000)
  })
  return Promise.race([promise, ceiling]).finally(() => clearTimeout(timer))
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  const vdir = join(args.flow, args.variant)
  const statePath = join(args.flow, '_state.json')
  let st = {}
  if (existsSync(statePath)) {
    try { st = JSON.parse(readFileSync(statePath, 'utf8')) || {} }
    catch (e) { console.error(`${statePath} exists but is not valid JSON (${e?.message || e}) - fix it before spending a pass`); process.exit(2) }
  }
  checkHarness(statePath, st, args.approveHarness)

  const { cases: all, path: casesPath, synthetic } = loadCases(args.flow)
  const unknown = args.only.filter((id) => !all.some((c) => c.id === id))
  if (unknown.length) { console.error(`--only: unknown case id(s) ${unknown.join(', ')}`); process.exit(2) }
  const cases = args.only.length ? all.filter((c) => args.only.includes(c.id)) : all
  const seen = new Set()
  for (const c of cases) {
    const k = c.id.toLowerCase()
    if (seen.has(k)) { console.error(`duplicate case id (case-insensitive): '${c.id}'`); process.exit(2) }
    seen.add(k)
  }

  mkdirSync(join(vdir, 'traces'), { recursive: true })
  const cfgPath = join(vdir, 'config.json')
  const cfg = { model: args.model, effort: args.effort ?? null, judge: !args.noJudge, cases: relative(process.cwd(), casesPath), synthetic }
  if (existsSync(cfgPath)) {
    const prev = JSON.parse(readFileSync(cfgPath, 'utf8'))
    if (prev.model !== cfg.model || prev.effort !== cfg.effort || prev.judge !== cfg.judge || prev.synthetic !== cfg.synthetic) {
      console.error(`${vdir} was run as ${JSON.stringify(prev)}; refusing to add ${JSON.stringify(cfg)} rows to it`)
      process.exit(2)
    }
  } else writeFileSync(cfgPath, JSON.stringify(cfg, null, 2) + '\n')

  const resultsPath = join(vdir, 'results.jsonl')
  const errorsPath = join(vdir, 'errors.jsonl')
  const done = new Set()
  if (existsSync(resultsPath))
    for (const ln of readFileSync(resultsPath, 'utf8').split('\n')) {
      if (!ln.trim()) continue
      try { const r = JSON.parse(ln); done.add(`${r.prompt_id}\0${r.rep}`) } catch {}
    }
  for (const p of [resultsPath, errorsPath]) {
    if (!existsSync(p)) continue
    const buf = readFileSync(p)
    if (buf.length && buf[buf.length - 1] !== 0x0a) appendFileSync(p, '\n')
  }
  const tasks = []
  for (const c of cases) for (let rep = 0; rep < args.reps; rep++) if (!done.has(`${c.id}\0${rep}`)) tasks.push({ c, rep })
  console.error(`[${args.variant}] ${tasks.length} of ${cases.length * args.reps} (id,rep) to run`)

  const ctx = { ...args, runNotePrompt: cases.some((c) => c.kind === 'run_note') ? loadRunNotePrompt() : null }
  let i = 0, ok = 0, fail = 0
  async function worker() {
    while (i < tasks.length) {
      const { c, rep } = tasks[i++]
      const t0 = Date.now()
      let lastRun = null
      let rowWritten = false
      const deadline = args.timeoutS > 0 ? t0 + args.timeoutS * 1000 : Infinity
      const appRetry = { count: 0 }, judgeRetry = { count: 0 }
      try {
        const { run, g, latency_s } = await withTimeout((async () => {
          let tAttempt = t0
          const run = await withBackoff(() => { tAttempt = Date.now(); return runCase(c, { ...ctx, rep }) }, appRetry, deadline)
          lastRun = run
          const latency_s = (Date.now() - tAttempt) / 1000
          const g = await withBackoff(() => gradeCase(c, run, ctx), judgeRetry, deadline)
          return { run, g, latency_s }
        })(), args.timeoutS, `${c.id} rep${rep}`)
        const row = {
          prompt_id: c.id, rep, kind: c.kind, pattern: c.pattern,
          // the athlete's wording stays in the gitignored output dir only
          prompt: c.kind === 'conversation' ? c.prompt : `run_note ${c.activity_id} ${c.date}`,
          meta: { ...(appRetry.count ? { retries: appRetry.count } : {}), ...(judgeRetry.count ? { judge_retries: judgeRetry.count } : {}),
                  effort: ctx.effort ?? null, synthetic, judge_cost_usd: g.judge_cost_usd ?? null,
                  output_written: run.output != null, tools_used: run.tools_used },
          model: run.model, usage: run.usage, stop_reason: run.stop_reason,
          status: run.stop_reason === 'max_tokens' ? 'truncated' : 'ok',
          judge_model: g.judge_model, judge_usage: g.judge_usage,
          latency_s, cost_usd: run.cost_usd, num_turns: run.num_turns,
          grade: g.grade, explanation: g.explanation,
        }
        appendFileSync(resultsPath, JSON.stringify(row) + '\n')
        rowWritten = true
        writeFileSync(join(vdir, 'traces', `${c.id}_rep${rep}.json`), JSON.stringify(run.transcript, null, 2))
        ok++
      } catch (e) {
        fail++
        if (rowWritten) { console.error(`  [${args.variant}] ${c.id} rep${rep} scored, but a post-row write failed: ${e?.message || e}`); continue }
        appendFileSync(errorsPath, JSON.stringify({
          prompt_id: c.id, rep, failure_class: e?.failure_class ?? 'error', error: String(e?.message || e),
          retries: appRetry.count, judge_retries: judgeRetry.count,
          model: lastRun?.model ?? e?.model, usage: lastRun?.usage ?? e?.usage,
          judge_model: e?.judge_model, judge_usage: e?.judge_usage, latency_s: (Date.now() - t0) / 1000,
        }) + '\n')
        console.error(`  [${args.variant}] ${c.id} rep${rep} FAILED: ${e?.message || e}`)
      }
    }
  }
  const t0 = Date.now()
  const progress = () => {
    const n = ok + fail, total = tasks.length, el = (Date.now() - t0) / 1000
    const eta = n ? Math.round((el / n) * (total - n)) : null
    const line = `[${args.variant}] ${n}/${total} done (${ok} ok, ${fail} failed), ${Math.round(el)}s elapsed` + (eta != null ? `, ~${eta}s left` : '')
    console.error(line)
    try { writeFileSync(join(vdir, 'progress.txt'), line + '\n') } catch {}
  }
  const tick = setInterval(progress, 30_000)
  await Promise.all(Array.from({ length: Math.max(1, args.concurrency) }, worker))
  clearInterval(tick); progress()
  console.error(`[${args.variant}] done - ${ok} ok, ${fail} failed -> ${resultsPath}`)
  process.exit(fail ? 1 : 0)
}

// Importable (the tests use loadCases / toolPermissions); runs only as a script.
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main()
