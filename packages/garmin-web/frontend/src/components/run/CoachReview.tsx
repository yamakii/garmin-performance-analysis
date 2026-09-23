import type { JSX } from "react";
import CoachNote from "../CoachNote";
import EmptyState from "../EmptyState";
import SectionBlock from "../SectionBlock";
import MarkdownText from "../report/MarkdownText";
import { isRecord } from "../report/ReportCard";
import NextSessionCard from "./NextSessionCard";
import type {
  GroundedPoint,
  NextSession,
  RunMoment,
  RunNote,
  SectionResult,
} from "../../types";
import { splitLead } from "../../utils/leadSentence";

/** Evidence prefix marking a point about what keeps coming back (#1251). */
const RECURRENCE_EVIDENCE = "recurrence.";

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

/** The grounded points of one list, dropping anything malformed. */
function points(value: unknown): GroundedPoint[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    const text = isRecord(item) ? asString(item.text) : null;
    if (text == null) {
      return [];
    }
    const evidence = isRecord(item) ? (asString(item.evidence) ?? "") : "";
    return [{ text, evidence }];
  });
}

/**
 * The coach's note as written by the agent, or null for a run that has none.
 *
 * Every field is read defensively: a legacy analysis, a parse error or a
 * half-written section must leave the rest of the page standing rather than
 * take it down (#1252).
 */
export function parseRunNote(section: SectionResult | undefined): RunNote | null {
  const data = section?.data;
  if (!isRecord(data)) {
    return null;
  }
  const story = asString(data.story);
  const nextChallenge = asString(data.next_challenge);
  if (story == null && nextChallenge == null) {
    return null;
  }
  return {
    story: story ?? "",
    good_points: points(data.good_points),
    growth_points: points(data.growth_points),
    next_challenge: nextChallenge ?? "",
    timeline: Array.isArray(data.timeline)
      ? data.timeline.flatMap((item) => {
          const momentId = isRecord(item) ? asString(item.moment_id) : null;
          const text = isRecord(item) ? asString(item.text) : null;
          return momentId != null && text != null
            ? [{ moment_id: momentId, text }]
            : [];
        })
      : [],
    notes: Array.isArray(data.notes)
      ? data.notes.flatMap((item) => {
          const signal = isRecord(item) ? asString(item.signal) : null;
          const text = isRecord(item) ? asString(item.text) : null;
          return signal != null && text != null ? [{ signal, text }] : [];
        })
      : [],
    question: isRecord(data) ? asString(data.question) : null,
    ...(reportMoments(data.report_moments) ?? {}),
  };
}

/**
 * `{report_moments}` when the note carries a usable scene snapshot (#1328),
 * or null so the page keeps the live report's scenes. Usable means a
 * non-empty array whose every scene has a string `id` and `kind`: anything
 * less could not be matched against the timeline, and a half-broken snapshot
 * is worse than the live scenes the page showed before #1328.
 */
function reportMoments(value: unknown): { report_moments: RunMoment[] } | null {
  if (!Array.isArray(value) || value.length === 0) {
    return null;
  }
  const usable = value.every(
    (item) =>
      isRecord(item) &&
      asString(item.id) != null &&
      asString(item.kind) != null,
  );
  return usable ? { report_moments: value as RunMoment[] } : null;
}

/** One bullet of the review: its marker, then the sentence. */
function Point({ marker, text }: { marker: string; text: string }) {
  return (
    <li className="flex gap-2 text-[15px] leading-[1.7] text-ink-soft">
      <span aria-hidden="true" className="font-mono text-ink-muted">
        {marker}
      </span>
      <span className="min-w-0">
        <MarkdownText inline>{text}</MarkdownText>
      </span>
    </li>
  );
}

function PointList({
  title,
  marker,
  items,
}: {
  title: string;
  marker: string;
  items: GroundedPoint[];
}): JSX.Element | null {
  if (items.length === 0) {
    return null;
  }
  return (
    <div>
      <h3 className="font-mono text-xs text-ink-muted">{title}</h3>
      <ul className="mt-2 flex flex-col gap-1.5">
        {items.map((point) => (
          <Point key={point.text} marker={marker} text={point.text} />
        ))}
      </ul>
    </div>
  );
}

/**
 * The legacy summary section, shown when a run predates the coach's note.
 *
 * An un-analysed or legacy run must not blank the top of the page: the old
 * section's opening sentence and its next action still say something, and
 * when even those are missing one line says so and the page carries on.
 */
function LegacyReview({
  section,
}: {
  section: SectionResult | undefined;
}): JSX.Element {
  const data = section?.data;
  const summary = isRecord(data) ? asString(data.summary) : null;
  const nextAction = isRecord(data) ? asString(data.next_action) : null;
  if (summary == null && nextAction == null) {
    return <EmptyState message="このランの総評はまだありません" />;
  }
  const lead = summary != null ? splitLead(summary).lead : null;
  return (
    <div className="flex flex-col gap-4">
      {lead != null && lead !== "" && (
        <p className="max-w-[720px] text-[15px] leading-[1.7] text-ink-soft">
          <MarkdownText inline>{lead}</MarkdownText>
        </p>
      )}
      {nextAction != null && <CoachNote strong>{nextAction}</CoachNote>}
    </div>
  );
}

/**
 * コーチの総評 — the one block of prose the page is written around (#1252).
 *
 * The five graded sections it replaces each restated the same run in their own
 * voice; what a reader wants first is what the run was for, what it did well,
 * what there is to grow, and the one point to carry over. Those come from the
 * single `run_note` section.
 *
 * A point grounded in `recurrence.*` is lifted out of its list into a line of
 * its own: "this keeps happening" is a different statement from "this went
 * well today", and it is the one the reader acts on across runs.
 *
 * 持ち越す 1 点 (#1358) is a cue from today, not a target for the next
 * session -- a single run cannot set that; the plan does. So the session the
 * athlete does next stands in its own block, and only when the plan names it
 * (`source` prescription / ladder). A same-type projection of today's run
 * (`next_run_target`) is not a plan and is not shown here.
 */
export default function CoachReview({
  id,
  note,
  legacySummary,
  nextSession = null,
}: {
  id?: string;
  note: RunNote | null;
  /** The old `summary` section, used only when there is no `run_note`. */
  legacySummary: SectionResult | undefined;
  /** Null on a report older than #1273, or when the plan says nothing. */
  nextSession?: NextSession | null;
}): JSX.Element {
  if (note == null) {
    return (
      <SectionBlock id={id} title="コーチの総評">
        <LegacyReview section={legacySummary} />
      </SectionBlock>
    );
  }

  const isRecurrence = (point: GroundedPoint) =>
    point.evidence.startsWith(RECURRENCE_EVIDENCE);
  const recurrence =
    note.growth_points.find(isRecurrence) ?? note.good_points.find(isRecurrence);
  const good = note.good_points.filter((point) => point !== recurrence);
  const growth = note.growth_points.filter((point) => point !== recurrence);
  const scheduled =
    nextSession != null && nextSession.source !== "same_type"
      ? nextSession
      : null;

  return (
    <SectionBlock id={id} title="コーチの総評">
      <div className="flex max-w-[720px] flex-col gap-5">
        {note.story !== "" && (
          <p className="text-[15px] leading-[1.7] text-ink-soft">
            <MarkdownText inline>{note.story}</MarkdownText>
          </p>
        )}
        <PointList title="良かった点" marker="✓" items={good} />
        <PointList title="伸ばせる点" marker="→" items={growth} />
        {recurrence != null && (
          <p className="text-[15px] leading-[1.7] text-ink-soft">
            <span className="font-mono text-xs text-ink-muted">繰り返し </span>
            <MarkdownText inline>{recurrence.text}</MarkdownText>
          </p>
        )}
        {note.next_challenge !== "" && (
          <div className="flex flex-col gap-3">
            <h3 className="font-mono text-xs text-ink-muted">持ち越す 1 点</h3>
            <CoachNote strong>{note.next_challenge}</CoachNote>
          </div>
        )}
        {scheduled != null && (
          <div data-testid="next-session-block">
            <NextSessionCard session={scheduled} />
          </div>
        )}
        {note.question != null && note.question !== "" && (
          <div>
            <h3 className="font-mono text-xs text-ink-muted">確認したいこと</h3>
            <p className="mt-2 text-[15px] leading-[1.7] text-ink-soft">
              <MarkdownText inline>{note.question}</MarkdownText>
            </p>
          </div>
        )}
      </div>
    </SectionBlock>
  );
}
