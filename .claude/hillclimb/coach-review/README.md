# coach-review eval

A regression eval for coaching behaviour. A change to the run-report contract, the
`run-note-analyst` agent, a skill or a rule can be measured against known failure
cases here, so the athlete is not the one who finds the regression. The layout
follows `../trend-narration/`.

## Case kinds

- **`run_note`**: runs `run-note-analyst` headless for an `activity_id`
  (`claude -p --agent run-note-analyst`). The prompt is the workflow's own
  `buildRunNotePrompt`, taken from the `// >>> testable` block of
  `.claude/workflows/analyze-activity.js`. The analyst writes `run_note.json` to a
  scratch dir under the system temp dir, and that file is graded. **Nothing is
  merged.** The two merge gates (section schema + grounding) run through the
  read-only CLI `garmin_mcp.scripts.check_run_note --report <json> --note <json>`.
- **`conversation`**: a single-turn probe, `claude -p "<athlete question>"` in the
  repo root, so CLAUDE.md and the rules load. Only **read-only** tools are allowed:
  Read / Glob / Grep and the garmin-db `get_*`, `export` and `prefetch_*` tools.
  Every other garmin-db tool (taken from the tool registry snapshot, so a new
  write tool is denied by default), Bash, Write, Edit, subagents, and the github /
  serena servers are on the deny list. The final answer is graded.

The harness never writes to DuckDB.

## Cases and the public repo

The repository is public, so the repo carries only the mechanism:

| File | In git | Contents |
|------|--------|----------|
| `cases.schema.json` | yes | the case shape |
| `cases.example.json` | yes | two synthetic cases (one per kind) |
| `cases.local.json` | **no** (gitignored) | the real cases: activity ids, the athlete's wording, expectations derived from incidents |
| `<variant>/` | **no** (gitignored) | results, traces, outputs, report copies |

The runner uses `cases.local.json` when it exists. Without it, it falls back to the
example and warns: those results are synthetic and measure nothing.

Each case names the generic failure pattern it guards against:

- **A**: a label, rule or profile note relayed as a conclusion;
- **B**: evidence quality not self-checked (cross-sensor or cross-period comparisons, derived values treated as confirmation);
- **C**: an uncalibrated stance (conservative by default, full reversal on pushback);
- **D**: context the athlete stated is lost;
- **E**: scope drift.

The judge rubric in `grade.mjs` only knows these abstract patterns. Athlete
specifics enter only through each case's `expect` strings, which stay local.

## Graders (`grade.mjs`)

- Deterministic (free):
  - `output_ok`;
  - `schema_ok` and `grounding_ok` (run_note only, via `check_run_note`);
  - `forbid_regex_ok`;
  - `growth_point_kinds_ok` (no growth point cites a moment whose `kind` is listed in `forbid_growth_point_moment_kinds`);
  - `required_evidence_ok` (every `required_evidence_prefixes` entry starts at least one cited evidence key).
- Judge (`claude-fable-5-1`, not a model under test): `must_ok` and `must_not_ok`
  over the case's `expect.must` / `expect.must_not`. The judge sees the run report
  and CONTEXT (run_note) or the probe's tool results (conversation).
- `case_pass` (the headline): every applicable metric passes. `null` means not applicable.
- Outcome rubric (#1546, Epic #1544): the judge also scores, 0 / 1 / 2, the outcomes a good
  coach output achieves from the athlete's side (`OUTCOMES` in `grade.mjs`):
  - O1 meaning (run_note)
  - O2 trust (both kinds)
  - O3 weighting (run_note)
  - O4 one thing to carry (run_note)
  - O5 own context (both kinds)
  - O6 delivery (both kinds)
  - O7 intent (conversation)

  Every case is judged for these, including cases that have no `must` / `must_not` items. The
  scores land in `grade.rubric`, with reasons in `explanation.rubric`. An unscored outcome reads
  `null`. The rubric sits beside `case_pass` and is not part of it. `compare.mjs` prints the mean
  per outcome. Rows graded before the rubric existed get it from `regrade.mjs <variant> --rejudge`.

Case expectations are written in principle form: what the output must base a claim on, or what it
must not conclude without checking. Never write the wording of one conclusion as an expectation.
Where the right answer differs between similar runs, add both as a contrastive pair
(`.claude/rules/dev/coach-incident-protocol.md`).

## Incident log and indicators (Epic #1544)

Every coach incident becomes a case (`.claude/rules/dev/coach-incident-protocol.md`), so the cases are
also the incident log. The optional fields `logged`, `source` (`owner` | `self` | `eval`), `triage`
(`code` | `principle` | `missing_principle` | `variance`) and `recurs_of` (an earlier case id) are never
sent to a model. `node $F/indicators.mjs [--since YYYY-MM-DD]` prints, with no model calls:

- incidents and owner corrections per ISO week, the count per triage class and the recurrence rate;
- eval regressions: cases that passed in an earlier variant and fail in the latest variant that ran them.

The rule-size side is `garmin_mcp.scripts.rule_budget` (`--history` for the weekly trend).

## Running

Every case's `claude -p` runs with `MCP_CONNECTION_NONBLOCKING=false`, so the session waits for
garmin-db to connect. A `--agent run-note-analyst` session has no ToolSearch to wait with; without
this setting it starts with no garmin-db tools and writes nothing (#1532). A run_note case that
never calls a `mcp__garmin-db__*` tool is recorded as `failure_class: "harness"` and is not graded.

**This spends Max usage (Claude Code login).** Every case is one headless session plus
one judge call. Ask the athlete before a full run. The first run after any harness
change must be started by a human with `--approve-harness`. The harness covers this
runner plus `_state.json` → `harness_paths`, which include `cases.local.json`.

```bash
F=.claude/hillclimb/coach-review
node $F/run-eval.mjs --flow $F --variant baseline --model opus --effort medium --only <id>   # pilot one case
node $F/run-eval.mjs --flow $F --variant baseline --model opus --effort medium
node $F/compare.mjs                 # every metric, per-pattern case_pass, cost, paired vs baseline
```

Flags (same as trend-narration):

- `--only id,id` runs a subset;
- `--no-judge` skips the model-graded metrics;
- `--reps N` repeats each case;
- `--concurrency N` sets how many cases run at once (default 2);
- `--timeout-s N` sets the per-case wall-clock ceiling.

Runs resume at the (case, rep) key. A variant directory is one configuration
(`config.json`), and the runner refuses to mix another into it. After changing the
deterministic graders or a case's deterministic `expect` fields,
`node $F/regrade.mjs <variant>` re-scores stored outputs without any model calls.
`--rejudge` re-runs the judge.
