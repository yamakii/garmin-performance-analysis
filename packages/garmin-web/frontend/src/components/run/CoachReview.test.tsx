import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CoachReview, { parseRunNote } from "./CoachReview";
import type { NextSession, RunNote, SectionResult } from "../../types";

/** The 9/20 long run the 2026-09-18 easy run actually led into (#1267). */
const NEXT_SESSION: NextSession = {
  date: "2026-09-20",
  days_ahead: 2,
  session_type: "long",
  session_label_ja: "ロング走",
  title: "ロング 16km",
  target_km: 16,
  target_minutes: null,
  hr_low: null,
  hr_high: 150,
  source: "prescription",
};

const NOTE: RunNote = {
  story:
    "ブロック3週目の土台づくりとして、ロングの前日に脚を動かしておく一本でした。狙いどおり軽い負荷で収まっています。",
  good_points: [
    { text: "心拍が終始ゾーン2に収まりました。", evidence: "plan.hr_ceiling" },
    { text: "ケイデンスが最後まで落ちませんでした。", evidence: "signals.cadence" },
  ],
  growth_points: [
    { text: "入りの1kmが少し速すぎました。", evidence: "moments.m1" },
  ],
  next_challenge:
    "入りは上限の150に近づく前に、意識してペースを抑えて走りましょう。",
  next_challenge_evidence: "moments.m1",
  timeline: [{ moment_id: "m1", text: "序盤から入りました。" }],
  notes: [],
  question: "前日の睡眠はどうでしたか？",
};

function renderReview(ui: Parameters<typeof render>[0]) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

function section(data: Record<string, unknown>): SectionResult {
  return { data, parse_error: false, raw: null };
}

describe("CoachReview", () => {
  it("test_coach_review_renders_all_parts", () => {
    renderReview(
      <CoachReview note={NOTE} legacySummary={undefined} />,
    );

    expect(screen.getByText(NOTE.story)).toBeInTheDocument();
    expect(screen.getByText("良かった点")).toBeInTheDocument();
    for (const point of NOTE.good_points) {
      expect(screen.getByText(point.text)).toBeInTheDocument();
    }

    // A growth point is marked as a direction to take, not as a failure.
    expect(screen.getByText("伸ばせる点")).toBeInTheDocument();
    const growth = screen.getByText(NOTE.growth_points[0].text);
    expect(growth.closest("li")).toHaveTextContent("→");

    expect(screen.getByText("持ち越す 1 点")).toBeInTheDocument();
    expect(screen.getByText(NOTE.next_challenge)).toBeInTheDocument();

    expect(screen.getByText("確認したいこと")).toBeInTheDocument();
    expect(screen.getByText(NOTE.question as string)).toBeInTheDocument();

    // No score anywhere: the page grades nothing (#1247).
    expect(screen.queryByLabelText(/^評価/)).not.toBeInTheDocument();
  });

  it("test_coach_review_omits_growth_when_empty", () => {
    renderReview(
      <CoachReview
        note={{ ...NOTE, growth_points: [] }}
        legacySummary={undefined}
      />,
    );

    // Nothing to grow is a valid run: the heading disappears rather than
    // standing empty and inviting an invented weakness.
    expect(screen.queryByText("伸ばせる点")).not.toBeInTheDocument();
    expect(screen.getByText("良かった点")).toBeInTheDocument();
  });

  it("test_coach_review_heading_is_carry_over", () => {
    renderReview(<CoachReview note={NOTE} legacySummary={undefined} />);

    // One point carried over from today, not a target for the next session
    // (#1358): the old heading is gone and no card hangs under the sentence.
    expect(screen.getByText("持ち越す 1 点")).toBeInTheDocument();
    expect(screen.queryByText("次回のチャレンジ")).not.toBeInTheDocument();
    expect(screen.queryByText("次回への処方")).not.toBeInTheDocument();
  });

  it("test_next_session_block_only_for_planned_session", () => {
    const { unmount } = renderReview(
      <CoachReview
        note={NOTE}
        legacySummary={undefined}
        nextSession={NEXT_SESSION}
      />,
    );

    // The plan's next session stands in its own block.
    const block = screen.getByTestId("next-session-block");
    expect(block).toHaveTextContent("次のセッション");
    expect(block).toHaveTextContent("9/20（2日後）");
    expect(block).toHaveTextContent("16 km");
    expect(block).toHaveTextContent("150 bpm 以下");
    unmount();

    // A same-type projection of today's run is not a plan: nothing shows.
    renderReview(
      <CoachReview
        note={NOTE}
        legacySummary={undefined}
        nextSession={{
          ...NEXT_SESSION,
          date: null,
          days_ahead: null,
          session_type: "aerobic_base",
          session_label_ja: "ベース走",
          title: null,
          target_km: null,
          source: "same_type",
        }}
      />,
    );
    expect(screen.queryByTestId("next-session-block")).toBeNull();
    expect(screen.queryByText("次回への処方")).not.toBeInTheDocument();
  });

  it("shows the next session even without a carried-over point", () => {
    renderReview(
      <CoachReview
        note={{ ...NOTE, next_challenge: "" }}
        legacySummary={undefined}
        nextSession={NEXT_SESSION}
      />,
    );

    expect(screen.queryByText("持ち越す 1 点")).not.toBeInTheDocument();
    expect(screen.getByTestId("next-session-block")).toBeInTheDocument();
  });

  it("lifts a recurrence point out of its list", () => {
    renderReview(
      <CoachReview
        note={{
          ...NOTE,
          growth_points: [
            { text: "3週続けて7km地点で失速しています。", evidence: "recurrence.fade" },
          ],
        }}
        legacySummary={undefined}
      />,
    );

    // "This keeps happening" is a different statement from "this went well
    // today", so it gets its own line instead of a bullet.
    const line = screen.getByText("3週続けて7km地点で失速しています。");
    expect(line.closest("li")).toBeNull();
    expect(screen.queryByText("伸ばせる点")).not.toBeInTheDocument();
  });

  it("test_coach_review_legacy_fallback", () => {
    renderReview(
      <CoachReview
        note={null}
        legacySummary={section({
          summary:
            "処方どおりの22kmを走り切れた一本でした。後半も心拍は上限内に収まっています。",
          next_action: "次回は最初の3kmを7:00/kmより遅く入りましょう。",
        })}
      />,
    );

    // A run analysed before the coach's note existed still says something.
    expect(
      screen.getByText("処方どおりの22kmを走り切れた一本でした。"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("次回は最初の3kmを7:00/kmより遅く入りましょう。"),
    ).toBeInTheDocument();
  });

  it("says so when there is no review at all", () => {
    renderReview(
      <CoachReview note={null} legacySummary={undefined} />,
    );

    expect(
      screen.getByText("このランの総評はまだありません"),
    ).toBeInTheDocument();
  });
});

describe("parseRunNote", () => {
  it("test_parse_run_note_survives_a_half_written_section", () => {
    const note = parseRunNote(
      section({
        story: "ロングの前日に脚を動かしておく一本でした。",
        good_points: [{ text: "心拍が安定していました。" }, "junk"],
        timeline: [{ moment_id: "m1" }, { moment_id: "m2", text: "後半。" }],
        notes: null,
      }),
    );

    expect(note?.good_points).toEqual([
      { text: "心拍が安定していました。", evidence: "" },
    ]);
    expect(note?.timeline).toEqual([{ moment_id: "m2", text: "後半。" }]);
    expect(note?.notes).toEqual([]);
    // A legacy section (or a parse error) simply has no note.
    expect(parseRunNote(section({ star_rating: "★★★★☆ 4.2/5.0" }))).toBeNull();
    expect(parseRunNote(undefined)).toBeNull();
  });
});

describe("parseRunNote report_moments (#1328)", () => {
  const section = (reportMoments: unknown): SectionResult => ({
    data: {
      story: "有酸素のロング走でした。",
      next_challenge: "次回も落ち着いて入りましょう。",
      report_moments: reportMoments,
    },
    parse_error: false,
    raw: null,
  });

  it("parses report_moments when present", () => {
    const scenes = [{ id: "m1", kind: "steady", label_ja: "0–5 km" }];
    expect(parseRunNote(section(scenes))?.report_moments).toEqual(scenes);
  });

  it("drops a malformed or empty snapshot", () => {
    // Unusable snapshots leave the page on the live scenes.
    for (const value of [
      "m1",
      [],
      [{ kind: "steady" }],
      [{ id: "m1" }],
      [null],
    ]) {
      expect(parseRunNote(section(value))?.report_moments).toBeUndefined();
    }
  });
});
