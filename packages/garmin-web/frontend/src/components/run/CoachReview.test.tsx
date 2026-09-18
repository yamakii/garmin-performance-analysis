import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CoachReview, { parseRunNote } from "./CoachReview";
import type { RunNote, SectionResult } from "../../types";

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
    "次回は150bpmを超えないように、最初の1kmを7:00/kmより遅く入りましょう。",
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
      <CoachReview
        note={NOTE}
        legacySummary={undefined}
        nextRunTarget={{ recommended_type: "aerobic_base", target_hr_low: 140 }}
      />,
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

    expect(screen.getByText("次回のチャレンジ")).toBeInTheDocument();
    expect(screen.getByText(NOTE.next_challenge)).toBeInTheDocument();
    // The deterministic numbers sit under the sentence that quotes them.
    expect(screen.getByText("次回への処方")).toBeInTheDocument();

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
        nextRunTarget={null}
      />,
    );

    // Nothing to grow is a valid run: the heading disappears rather than
    // standing empty and inviting an invented weakness.
    expect(screen.queryByText("伸ばせる点")).not.toBeInTheDocument();
    expect(screen.getByText("良かった点")).toBeInTheDocument();
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
        nextRunTarget={null}
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
        nextRunTarget={null}
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
      <CoachReview note={null} legacySummary={undefined} nextRunTarget={null} />,
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
