#!/usr/bin/env node
// trend-narration eval runner (built from the claude-api build-eval scaffold).
//
// Runs the narration stage of .claude/workflows/trend-narration.js exactly as
// the workflow does - the prompt comes from the workflow's own testable block,
// the model runs as a headless Claude Code session in the repo root, and it
// prefetches CONTEXT with the real script - then grades the trend.json it wrote
// (grade.mjs). Run from the repo root:
//
//   node .claude/hillclimb/trend-narration/run-eval.mjs \
//     --flow .claude/hillclimb/trend-narration --variant baseline --model sonnet --reps 2
//   node ... --variant v1 --model opus --effort medium --reps 2
//
// --effort omitted = the user's settings decide (as in production, where the
// workflow's agent() passes no effort). --no-judge skips the model-graded
// metrics (they become null). --only id1,id2 restricts to a subset (pilot).
//
// Structural properties this encodes (so you don't have to remember them):
//   - parameterized by --variant / --model / --reps (no hardcoded A/B pair)
//   - rep-aware filenames + resume (traces/<id>_rep<k>.json)
//   - reads _state.json, never writes it (loop state belongs to the orchestrator) - 
//     the ONE exception is --approve-harness recording `harness_sha` (see below)
//   - refuses to run when the harness (this file + _state.json.harness_paths) has
//     changed since the sha a human last approved with --approve-harness, so a
//     round that edits the runner cannot execute unreviewed under a standing
//     session allowlist
//   - pairwise graders judge against frozen baseline/ref/<id>.* on disk
//   - writes rows as cases complete (crash-safe)
//   - jittered exponential backoff on transient 429/overloaded/5xx errors
//   - hard per-case wall-clock ceiling (--timeout-s; stream keepalives don't reset it)
//   - served-model assertion (response model must match --model; documented alias->snapshot
//     shapes tolerated: 'foo-latest'/'foo-0'/'foo' -> 'foo-20250101' / 'foo@20250101' / 'foo-2025-01-01')
//   - failed attempts land in errors.jsonl with a failure class and, when the call
//     completed, the billed model/usage (never in results.jsonl)
//   - row ids, trace filenames, and frozen refs share one path-safe id
//     (original id kept in meta.original_id when sanitization changed it)

import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { appendFileSync, copyFileSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { cleanEnv, combine, judge } from './grade.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const WORKFLOW = resolve(HERE, '../../workflows/trend-narration.js');

// The prompt is the workflow's own narrationPrompt (single source of truth),
// extracted the same way .claude/workflows/tests/trend-narration.test.mjs does.
function loadNarrationPrompt() {
  const src = readFileSync(WORKFLOW, 'utf8');
  const m = src.match(/\/\/ >>> testable\n([\s\S]*?)\n\s*\/\/ <<< testable/);
  if (!m) throw new Error('testable block markers not found in trend-narration.js');
  // eslint-disable-next-line no-new-func
  return new Function(`${m[1]}\nreturn narrationPrompt`)();
}
const narrationPrompt = loadNarrationPrompt();

async function loadCases(args) {
  const cases = JSON.parse(readFileSync(join(HERE, 'cases.json'), 'utf8'));
  const unknown = args.only.filter(id => !cases.some(c => c.id === id));
  if (unknown.length) { console.error(`--only: unknown case id(s) ${unknown.join(', ')}`); process.exit(2); }
  return (args.only.length ? cases.filter(c => args.only.includes(c.id)) : cases)
    .map(c => ({ ...c, prompt: `${c.granularity} ${c.period_start}..${c.period_end}` }));
}

// Served-model family check: the run is requested by alias (sonnet / opus) and
// served under a full id; auxiliary small-model calls Claude Code makes on its
// own are ignored, the main model is the one with the most output tokens.
function mainModel(modelUsage) {
  const e = Object.entries(modelUsage ?? {});
  e.sort((a, b) => (b[1].outputTokens ?? 0) - (a[1].outputTokens ?? 0));
  return e[0]?.[0] ?? null;
}

function toTranscript(events, prompt, meta) {
  const t = [{ role: 'system', content: `Claude Code default system prompt (headless, cwd=repo root). model=${meta.model} effort=${meta.effort ?? '(settings)'}` },
             { role: 'user', content: prompt }];
  const clip = (s) => (s.length > 6000 ? `${s.slice(0, 6000)}\n… [${s.length - 6000} chars clipped in trace]` : s);
  for (const ev of events) {
    const blocks = ev.message?.content;
    if (!Array.isArray(blocks)) continue;
    for (const b of blocks) {
      if (ev.type === 'assistant' && b.type === 'text' && b.text.trim()) t.push({ role: 'assistant', content: b.text });
      else if (ev.type === 'assistant' && b.type === 'tool_use')
        t.push({ role: 'tool_call', name: b.name, content: JSON.stringify(b.input, null, 2) });
      else if (ev.type === 'user' && b.type === 'tool_result') {
        const c = Array.isArray(b.content) ? b.content.map(x => x.text ?? '').join('\n') : String(b.content ?? '');
        t.push({ role: 'tool_result', content: clip(c) });
      }
    }
  }
  return t;
}

function runClaude(args, cwd, timeoutMs) {
  return new Promise((res, rej) => {
    const p = spawn('claude', args, { cwd, env: cleanEnv(), stdio: ['ignore', 'pipe', 'pipe'] });
    let out = '', err = '';
    const timer = setTimeout(() => p.kill('SIGTERM'), timeoutMs);
    p.stdout.on('data', d => (out += d));
    p.stderr.on('data', d => (err += d));
    p.on('close', code => { clearTimeout(timer); res({ code, out, err }); });
    p.on('error', e => { clearTimeout(timer); rej(e); });
  });
}

async function runCase(input, ctx) {
  const tempDir = join(tmpdir(), 'trend-eval', ctx.variant, `${input.id}_rep${ctx.rep}`);
  rmSync(tempDir, { recursive: true, force: true });
  const prompt = narrationPrompt({
    tempDir, periodStart: input.period_start, periodEnd: input.period_end, granularity: input.granularity,
  });
  const args = ['-p', prompt, '--model', ctx.model, '--output-format', 'stream-json', '--verbose',
    '--allowedTools', 'Bash', 'Read', 'Write', 'Edit', '--no-session-persistence'];
  if (ctx.effort) args.push('--effort', ctx.effort);
  const { code, out, err } = await runClaude(args, process.cwd(), ctx.timeoutS * 1000);
  const events = out.split('\n').filter(Boolean).flatMap(l => { try { return [JSON.parse(l)]; } catch { return []; } });
  const result = events.find(e => e.type === 'result');
  if (!result) {
    const e = new Error(`claude produced no result event (exit ${code}): ${err.slice(0, 300)}`);
    e.failure_class = 'harness';
    throw e;
  }
  const model = mainModel(result.modelUsage);
  const family = ctx.model.replace(/^claude-/, '').split('-')[0];
  if (!model || !model.includes(family)) {
    const e = new Error(`served model ${model} is not a ${family} model`);
    e.failure_class = 'serving_substitution';
    throw e;
  }
  const u = result.usage ?? {};
  const usage = { input_tokens: u.input_tokens ?? 0, output_tokens: u.output_tokens ?? 0,
    cache_read_input_tokens: u.cache_read_input_tokens ?? 0, cache_creation_input_tokens: u.cache_creation_input_tokens ?? 0 };
  // CONTEXT is the script's output, not the model's: a missing or failed
  // prefetch is plumbing, not a narration failure.
  let contextJson = null;
  try { contextJson = JSON.parse(readFileSync(join(tempDir, 'context.json'), 'utf8')); } catch {}
  if (!contextJson || contextJson.error) {
    const e = new Error(`context.json missing/invalid in ${tempDir}`);
    e.failure_class = 'harness';
    throw Object.assign(e, { usage, model });
  }
  let trend = null;
  try { trend = JSON.parse(readFileSync(join(tempDir, 'trend.json'), 'utf8')); } catch {}
  // Keep the model's output next to the results (the temp dir is scratch).
  const outRel = join(ctx.variant, 'out', `${input.id}_rep${ctx.rep}.trend.json`);
  const outAbs = join(ctx.flow, outRel);
  mkdirSync(dirname(outAbs), { recursive: true });
  if (trend) copyFileSync(join(tempDir, 'trend.json'), outAbs);
  // The CONTEXT the model saw, kept beside the output so programmatic metrics can
  // be re-graded later without re-running the model (regrade.mjs).
  copyFileSync(join(tempDir, 'context.json'), join(ctx.flow, ctx.variant, 'out', `${input.id}_rep${ctx.rep}.context.json`));
  const lastAssistant = [...events].reverse().find(e => e.type === 'assistant');
  const transcript = toTranscript(events, prompt, { model, effort: ctx.effort });
  if (trend) transcript.push({ role: 'assistant', content: '(trend.json written)', attachments: [{ kind: 'json', ref: outRel, alt: 'trend.json' }] });
  return {
    output: trend, trend, contextJson, transcript, model, usage, prompt,
    stop_reason: lastAssistant?.message?.stop_reason ?? result.subtype,
    cost_usd: result.total_cost_usd ?? null,
    num_turns: result.num_turns ?? null,
    context_sha: createHash('sha256').update(JSON.stringify(contextJson)).digest('hex').slice(0, 12),
    is_error: result.is_error === true,
  };
}

async function gradeCase(input, run, ref, ctx) {
  const j = ctx.noJudge ? null : await judge(input, run.contextJson, run.trend);
  const { grade, explanation } = combine(input, run.contextJson, run.trend, j, run.prompt);
  return { grade, explanation, judge_model: j?.judge_model, judge_usage: j?.judge_usage, judge_cost_usd: j?.judge_cost_usd ?? null };
}

function perfFrom(run) { return { cost_usd: run.cost_usd, num_turns: run.num_turns }; }

// --- harness (you usually won't need to touch below this line) --------------

function parseArgs(argv) {
  const a = { flow: '.claude/hillclimb/flow', variant: 'baseline',
              model: undefined, effort: undefined, noJudge: false, only: [],
              reps: 1, concurrency: 3, timeoutS: 900,
              approveHarness: false };
  // A flag at the end of argv would otherwise consume undefined - which for
  // --model equals the default and silently disables the served-model check.
  const val = (i) => { if (argv[i] === undefined) { console.error(`missing value for ${argv[i - 1]}`); usage(); process.exit(2); } return argv[i]; };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    if (k === '--flow') a.flow = val(++i);
    else if (k === '--variant') a.variant = val(++i);
    else if (k === '--model') a.model = val(++i);
    else if (k === '--reps') a.reps = +val(++i);
    else if (k === '--concurrency') a.concurrency = +val(++i);
    else if (k === '--timeout-s') a.timeoutS = +val(++i);
    else if (k === '--approve-harness') a.approveHarness = true;
    else if (k === '--effort') a.effort = val(++i);
    else if (k === '--no-judge') a.noJudge = true;
    else if (k === '--only') a.only = val(++i).split(',').filter(Boolean);
    else if (k === '-h' || k === '--help') { usage(); process.exit(0); }
    else { console.error(`unknown argument: ${k}`); usage(); process.exit(2); }
  }
  if (!/^(baseline|v[1-9]\d*)$/.test(a.variant)) {
    // The report only reads directories named 'baseline' or 'v<N>' - any other
    // name runs to completion but spends the pass into a directory the Summary,
    // trajectory, and budget arithmetic never see.
    console.error(`--variant must be 'baseline' or 'v<N>', got '${a.variant}'`);
    usage(); process.exit(2);
  }
  if (!a.model) { console.error('--model is required (sonnet | opus | a full model id)'); usage(); process.exit(2); }
  if (a.effort && !['low', 'medium', 'high', 'xhigh', 'max'].includes(a.effort)) { usage(); process.exit(2); }
  if (!Number.isFinite(a.timeoutS) || a.timeoutS < 0
      || a.timeoutS * 1000 > 2147483647 // setTimeout clamps >2^31-1 ms to 1 ms - the ceiling would fire instantly
      || !Number.isInteger(a.reps) || a.reps < 1
      || !Number.isInteger(a.concurrency) || a.concurrency < 1) { usage(); process.exit(2); }
  return a;
}
function usage() {
  console.error('usage: node run-eval.mjs --flow DIR --variant ID --model ID [--effort LEVEL] [--no-judge] [--only id,id] [--reps N] [--concurrency N] [--timeout-s N (0 = no ceiling)] [--approve-harness]');
}

// Harness integrity gate. The hillclimb loop gets this runner command
// allowlisted for the session and then runs rounds unattended, while the
// per-round change (proposed by an analyzer fed untrusted transcripts) may
// legitimately edit harness code. Without this gate a round that rewrites the
// runner would execute attacker-chosen code on the next unattended run under
// the user's one-time approval. So: sha256 over this file plus every path in
// `_state.json.harness_paths` (relative to the directory the runner is invoked
// from, i.e. the repo root); compare to `_state.json.harness_sha`; refuse on
// absent/mismatch unless a human passes --approve-harness, which records the
// new sha. That write is the one sanctioned exception to "never write
// _state.json".
function checkHarness(statePath, st, approve) {
  const self = fileURLToPath(import.meta.url);
  const listed = Array.isArray(st.harness_paths) ? st.harness_paths.map(String) : [];
  const paths = [...new Set([self, ...listed.map(p => resolve(p))])].sort();
  const h = createHash('sha256');
  const hashed = [];
  for (const p of paths) {
    let buf;
    try { buf = readFileSync(p); }
    catch (e) {
      if (p === self) throw e;
      console.error(`warning: harness path '${relative(process.cwd(), p)}' not readable (${e?.code || 'error'}) - skipped`);
      continue;
    }
    h.update(relative(process.cwd(), p)).update('\0').update(buf).update('\0');
    hashed.push(relative(process.cwd(), p));
  }
  const sha = h.digest('hex');
  if (st.harness_sha === sha) return;
  if (approve) {
    st.harness_sha = sha;
    writeFileSync(statePath, JSON.stringify(st, null, 2) + '\n');
    console.error(`harness approved: sha256 ${sha.slice(0, 12)} over ${hashed.length} file(s) recorded in ${statePath}`);
    return;
  }
  if (st.harness_sha == null) {
    console.error(`no approved harness sha in ${statePath} (computed ${sha.slice(0, 12)} over: ${hashed.join(', ')}).`);
    console.error('Review the harness, then run once with --approve-harness to record it.');
  } else {
    console.error(`harness changed since last approved run (files: ${hashed.join(', ')}); `
      + `approved ${String(st.harness_sha).slice(0, 12)}, now ${sha.slice(0, 12)}.`);
    console.error('Re-run with --approve-harness after reviewing the diff.');
  }
  process.exit(2);
}

// Transient provider errors (429 / overloaded / 5xx) retry with jittered
// exponential backoff - a zero-delay retry loop multiplies cost invisibly
// under rate limits and can turn one transient 429 into a torn-down batch.
// The attempt count lands in the row's meta (or the errors sidecar) so retry
// churn is visible in the data, not just the bill.
async function withBackoff(fn, retry, deadline = Infinity, tries = 5) {
  for (let attempt = 0; ; attempt++) {
    // Checked before every attempt, not just before sleeps: once the case's
    // ceiling has passed, an abandoned chain must not issue another call
    // (e.g. a judge call after the app call consumed the whole ceiling).
    if (Date.now() >= deadline) {
      const e = new Error('wall-clock ceiling exceeded before attempt');
      e.failure_class = 'timeout';
      throw e;
    }
    try { return await fn(); } catch (e) {
      const status = e?.status ?? e?.response?.status;
      const transient = status === 429 || status === 529 || (status >= 500 && status < 600)
        || /overloaded|rate.?limit/i.test(String(e?.message ?? ''));
      if (!transient || attempt >= tries - 1) throw e;
      const delay = Math.min(60_000, 1000 * 2 ** attempt) * (0.5 + Math.random());
      // Never start a retry that would outlive the case's wall-clock ceiling - 
      // otherwise an abandoned chain keeps issuing API calls after the case failed.
      if (Date.now() + delay >= deadline) throw e;
      retry.count++;
      await new Promise(r => setTimeout(r, delay));
    }
  }
}

// Hard per-case wall-clock ceiling, independent of stream liveness - a hung
// SSE stream can emit keepalives forever, defeating inactivity-based timers.
// The underlying call may keep running; the case fails and the slot is freed.
function withTimeout(promise, seconds, label) {
  if (!(seconds > 0)) return promise;
  let timer;
  const ceiling = new Promise((_, reject) => {
    timer = setTimeout(() => {
      const e = new Error(`${label}: exceeded ${seconds}s wall-clock ceiling`);
      e.failure_class = 'timeout';
      reject(e);
    }, seconds * 1000);
  });
  return Promise.race([promise, ceiling]).finally(() => clearTimeout(timer));
}

// Case ids appear in file paths AND as the row/file join key the report uses,
// so rows, trace filenames, and frozen refs all carry the same path-safe id.
// When sanitization changes the id, a short content hash keeps distinct ids
// distinct ('case/1' vs 'case_1'); the original rides in meta.original_id.
function pathSafeId(id) {
  const raw = String(id);
  const cleaned = raw.replace(/[^\w.-]/g, '_');
  // Idempotent by construction: anything already path-safe and within the
  // length bound - including this function's own truncated+suffixed output - 
  // passes through unchanged. Long ids (URLs, prompt text as id) truncate to
  // 120 chars plus an 8-hex hash of the full original, so they fail here, not
  // at the trace write after the spend, and distinct ids stay distinct.
  if (cleaned === raw && raw.length <= 129) return raw;
  return `${cleaned.slice(0, 120)}-${createHash('sha256').update(raw).digest('hex').slice(0, 8)}`;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const vdir = join(args.flow, args.variant);
  mkdirSync(join(vdir, 'traces'), { recursive: true });
  // _state.json is READ-ONLY here. The orchestrator owns it. Absent is fine
  // (a baseline-only run has no loop state yet), but present-and-unparsable
  // must not let the id-space gate below pass vacuously over a corrupt file.
  const statePath = join(args.flow, '_state.json');
  let st = {};
  if (existsSync(statePath)) {
    try { st = JSON.parse(readFileSync(statePath, 'utf8')) || {}; }
    catch (e) { console.error(`${statePath} exists but is not valid JSON (${e?.message || e}) - fix it before spending a pass`); process.exit(2); }
  }
  checkHarness(statePath, st, args.approveHarness);
  const ctx = { ...args, state: st };
  // A variant directory is one configuration; refuse to mix two into it.
  const cfgPath = join(vdir, 'config.json');
  const cfg = { model: args.model, effort: args.effort ?? null, judge: !args.noJudge };
  if (existsSync(cfgPath)) {
    const prev = JSON.parse(readFileSync(cfgPath, 'utf8'));
    if (prev.model !== cfg.model || prev.effort !== cfg.effort || prev.judge !== cfg.judge) {
      console.error(`${vdir} was run as ${JSON.stringify(prev)}; refusing to add ${JSON.stringify(cfg)} rows to it`);
      process.exit(2);
    }
  } else writeFileSync(cfgPath, JSON.stringify(cfg, null, 2) + '\n');

  // Resume: which (id, rep) pairs already have a row?
  const resultsPath = join(vdir, 'results.jsonl');
  const done = new Set();
  if (existsSync(resultsPath))
    for (const ln of readFileSync(resultsPath, 'utf8').split('\n')) {
      if (!ln.trim()) continue;
      try { const r = JSON.parse(ln); done.add(`${r.prompt_id}\0${r.rep}`); } catch {}
    }
  // Rows key on the path-safe id (see pathSafeId), so resume must too.

  const cases = await loadCases(args);
  // Validate the id space before spending anything: duplicate path-safe ids - 
  // including case-insensitive twins, which macOS/Windows filesystems collapse - 
  // would silently overwrite traces and frozen refs; and a _state.json split id
  // that matches no case would silently shrink the scored denominator.
  const seen = new Map();
  for (const c of cases) {
    const k = pathSafeId(c.id).toLowerCase();
    if (seen.has(k)) {
      console.error(`duplicate case id after sanitization: '${c.id}' collides with '${seen.get(k)}'`);
      process.exit(2);
    }
    seen.set(k, c.id);
  }
  const safeIds = new Set(cases.map(c => pathSafeId(c.id)));
  for (const sid of [...(st.train_ids ?? []), ...(st.val_ids ?? []), ...(st.test_ids ?? [])]) {
    const s = String(sid); // the adapter joins with String() on both sides - numeric ids are fine
    if (safeIds.has(s)) continue; // matches a loaded case - definitionally valid
    if (s !== pathSafeId(s)) {
      // Can never match a row: rows key on path-safe ids. This is the silent
      // shrunken-denominator bug - fail before anything is spent.
      console.error(`_state.json split id '${s}' is not a path-safe id - record split ids exactly as they appear in results.jsonl's prompt_id`);
      process.exit(2);
    }
    // Well-formed but absent is legitimate (a trimmed top-K subset run) - note it, don't fail.
    console.error(`note: split id '${s}' matches no loaded case (expected for a trimmed subset run)`);
  }
  const refDir = join(args.flow, 'baseline', 'ref');
  const tasks = [];
  for (const c of cases) for (let rep = 0; rep < args.reps; rep++) {
    if (done.has(`${pathSafeId(c.id)}\0${rep}`)) continue;
    tasks.push({ c, rep });
  }
  console.error(`[${args.variant}] ${tasks.length} of ${cases.length * args.reps} (id,rep) to run`);

  let i = 0, ok = 0, fail = 0;
  const errorsPath = join(vdir, 'errors.jsonl');
  // A hard crash (power loss, ENOSPC) can leave a torn final line with no
  // trailing newline; the next append would merge two rows into one permanently
  // unparseable line. Isolate any fragment before appending anything.
  for (const p of [resultsPath, errorsPath]) {
    if (!existsSync(p)) continue;
    const buf = readFileSync(p);
    if (buf.length && buf[buf.length - 1] !== 0x0a) appendFileSync(p, '\n');
  }
  async function worker() {
    while (i < tasks.length) {
      const { c, rep } = tasks[i++];
      const safeId = pathSafeId(c.id);
      const t0 = Date.now();
      let lastRun = null;    // survives into the catch - billed spend on a failed attempt
      let rowWritten = false; // set once the results row lands - the attempt is scored
      const deadline = args.timeoutS > 0 ? t0 + args.timeoutS * 1000 : Infinity;
      const appRetry = { count: 0 }, judgeRetry = { count: 0 };
      try {
        // One ceiling over the whole case - app call, identity check, and grading - 
        // so a hung judge stream can't hold the slot either.
        const { run, g, latency_s } = await withTimeout((async () => {
          let tAttempt = t0;
          const run = await withBackoff(() => { tAttempt = Date.now(); return runCase(c, { ...ctx, rep }); },
            appRetry, deadline);
          lastRun = run;
          // latency_s = the final app attempt only; backoff sleeps, failed
          // attempts, and judge time are excluded (retry counts are in meta).
          const latency_s = (Date.now() - tAttempt) / 1000;
          // Serving identity: fail loudly when the response was served by a model
          // other than the one requested. Accept exact match or a documented
          // alias->snapshot resolution - 'foo-latest'/'foo-0'/'foo' served as
          // 'foo-20250101', 'foo@20250101', or 'foo-2025-01-01'. Anything else - 
          // another snapshot of the requested pin, a sibling model, or the bare
          // base id ('foo-latest' served as 'foo', an unversioned echo that can
          // hide snapshot drift across rounds) - fails the attempt. Non-Anthropic
          // id schemes (e.g. Bedrock's 'anthropic.claude-...-v1:0') need their own
          // rule here.
          // (This flow requests models by Claude Code alias; the family check
          // lives in runCase, where the served model is read from modelUsage.)
          // Frozen pairwise reference (never regenerated): baseline/ref/<id>.*
          let ref = null;
          if (args.variant !== 'baseline') {
            const p = join(refDir, safeId);
            for (const ext of ['', '.html', '.txt', '.json'])
              if (existsSync(p + ext)) { ref = readFileSync(p + ext, 'utf8'); break; }
          }
          const g = await withBackoff(() => gradeCase(c, run, ref, ctx), judgeRetry, deadline);
          return { run, g, latency_s };
        })(), args.timeoutS, `${c.id} rep${rep}`);
        const row = {
          prompt_id: safeId, rep, prompt: c.prompt ?? c.input ?? c.id,
          tags: c.tags, attachments: c.attachments,
          meta: { ...(c.meta ?? {}),
                ...(safeId !== String(c.id) ? { original_id: String(c.id) } : {}),
                ...(appRetry.count ? { retries: appRetry.count } : {}),
                ...(judgeRetry.count ? { judge_retries: judgeRetry.count } : {}),
                // same sha across variants = they narrated the same CONTEXT
                context_sha: run.context_sha, effort: ctx.effort ?? null,
                judge_cost_usd: g.judge_cost_usd ?? null, trend_written: run.trend != null },
          model: run.model, usage: run.usage, stop_reason: run.stop_reason,
          status: run.stop_reason === 'max_tokens' ? 'truncated' : 'ok',
          judge_model: g.judge_model ?? run.judge_model,
          judge_usage: g.judge_usage ?? run.judge_usage,
          latency_s, ...perfFrom(run),
          grade: g.grade, explanation: g.explanation,
        };
        appendFileSync(resultsPath, JSON.stringify(row) + '\n');
        rowWritten = true; // past this point the attempt is scored - a later throw (trace write, ref freeze) must not also append an error row
        if (run.transcript)
          writeFileSync(join(vdir, 'traces', `${safeId}_rep${rep}.json`),
            JSON.stringify(run.transcript, null, 2));
        // For pairwise: on the baseline run, freeze the reference output once.
        if (args.variant === 'baseline' && run.output != null && !existsSync(join(refDir, safeId))) {
          mkdirSync(refDir, { recursive: true });
          writeFileSync(join(refDir, safeId),
            typeof run.output === 'string' ? run.output : JSON.stringify(run.output));
        }
        ok++;
      } catch (e) {
        fail++;
        if (rowWritten) {
          // The attempt scored; only a post-row write (trace, ref) failed. An error
          // row here would double-count the billed usage under the budget rule.
          console.error(`  [${args.variant}] ${c.id} rep${rep} scored, but a post-row write failed: ${e?.message || e}`);
          continue;
        }
        // Failed attempts are data too - but they must not occupy the (case, rep)
        // slot in results.jsonl, or resume would never re-run them.
        appendFileSync(errorsPath, JSON.stringify({
          prompt_id: safeId, rep,
          ...(safeId !== String(c.id) ? { original_id: String(c.id) } : {}),
          failure_class: e?.failure_class ?? 'error',
          error: String(e?.message || e),
          retries: appRetry.count, judge_retries: judgeRetry.count,
          // Billed-but-failed spend stays countable: when the app call completed
          // before the failure (e.g. a served-model mismatch, a judge-stage
          // ceiling), carry its identity and usage on the error row.
          model: lastRun?.model, usage: lastRun?.usage,
          judge_model: e?.judge_model ?? lastRun?.judge_model,
          judge_usage: e?.judge_usage ?? lastRun?.judge_usage,
          latency_s: (Date.now() - t0) / 1000,
        }) + '\n');
        console.error(`  [${args.variant}] ${c.id} rep${rep} FAILED: ${e?.message || e}`);
      }
    }
  }
  // One progress line every 30s (and to <vdir>/progress.txt) so "how far along
  // is it?" is answerable from the background shell's output or one file read,
  // without the orchestrator parsing results.jsonl mid-write. ETA is a plain
  // rate extrapolation from this pass.
  const t0 = Date.now();
  const progress = () => {
    const done = ok + fail, total = tasks.length;
    const el = (Date.now() - t0) / 1000;
    const eta = done ? Math.round((el / done) * (total - done)) : null;
    const line = `[${args.variant}] ${done}/${total} done (${ok} ok, ${fail} failed), `
      + `${Math.round(el)}s elapsed` + (eta != null ? `, ~${eta}s left` : '');
    console.error(line);
    try { writeFileSync(join(vdir, 'progress.txt'), line + '\n'); } catch {}
  };
  const tick = setInterval(progress, 30_000);
  await Promise.all(Array.from({ length: Math.max(1, args.concurrency) }, worker));
  clearInterval(tick); progress();
  console.error(`[${args.variant}] done - ${ok} ok, ${fail} failed -> ${resultsPath}`);
  process.exit(fail ? 1 : 0);
}

main();
