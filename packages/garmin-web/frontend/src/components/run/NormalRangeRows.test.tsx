import { MemoryRouter } from "react-router-dom";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import NormalRangeRows from "./NormalRangeRows";
import type { RunSignal } from "../../types";

function signal(overrides: Partial<RunSignal> & { metric: string }): RunSignal {
  return {
    family: "form",
    label_ja: overrides.metric,
    unit: "ms",
    today: 260,
    expected: 255,
    normal_low: 248,
    normal_high: 262,
    z: 0.4,
    status: "within",
    adverse: false,
    streak: 0,
    reason: null,
    ...overrides,
  };
}

const SIGNALS: RunSignal[] = [
  signal({ metric: "gct", label_ja: "接地時間", status: "within", z: 0.3 }),
  signal({
    metric: "vo",
    label_ja: "上下動",
    unit: "cm",
    today: 8.4,
    normal_low: 7.9,
    normal_high: 8.5,
    status: "edge",
    z: 1.2,
  }),
  signal({
    metric: "vr",
    label_ja: "上下動比",
    unit: "%",
    today: 7.9,
    normal_low: 7.0,
    normal_high: 7.6,
    status: "outside",
    adverse: true,
    z: 2.4,
  }),
  signal({
    family: "cardio",
    metric: "hr_vs_expected",
    label_ja: "心拍（想定比）",
    unit: "bpm",
    today: -6,
    normal_low: -4,
    normal_high: 5,
    status: "outside",
    adverse: false,
    z: -2.1,
  }),
  signal({
    family: "cardio",
    metric: "hr_drift",
    label_ja: "心拍ドリフト",
    unit: "%",
    today: 4.2,
    normal_low: null,
    normal_high: null,
    z: null,
    status: "insufficient",
    reason: "only 3 running splits (need 5)",
  }),
];

function renderRows(
  signals: RunSignal[],
  notes: { signal: string; text: string }[] = [],
) {
  return render(
    <MemoryRouter>
      <NormalRangeRows
        signals={signals}
        zones={[
          { zone: 1, pct: 8.2 },
          { zone: 2, pct: 74.5 },
          { zone: 3, pct: 17.3 },
        ]}
        notes={notes}
      />
    </MemoryRouter>,
  );
}

/** The `<li>` a metric's row is drawn in. */
function rowOf(label: string): HTMLElement {
  const row = screen.getByText(label).closest("li");
  if (row == null) throw new Error(`no row for ${label}`);
  return row;
}

describe("NormalRangeRows", () => {
  it("test_signal_row_tails", () => {
    renderRows(SIGNALS);

    expect(rowOf("接地時間")).toHaveTextContent("いつもの範囲");
    expect(rowOf("上下動")).toHaveTextContent("高い側の端");
    expect(rowOf("上下動比")).toHaveTextContent("範囲外（高い側）");
    // A favourable outlier is good news, so it is never dressed up as one.
    expect(rowOf("心拍（想定比）")).toHaveTextContent("良い側に外れ");
    expect(rowOf("心拍ドリフト")).toHaveTextContent("判定対象外");
    // Silence is explained rather than left as a blank row.
    expect(rowOf("心拍ドリフト")).toHaveTextContent(
      "only 3 running splits (need 5)",
    );

    // Colour marks the exception, and only the adverse one is an exception.
    for (const label of ["接地時間", "上下動", "心拍（想定比）", "心拍ドリフト"]) {
      expect(
        rowOf(label).querySelector(".text-status-warn"),
      ).toBeNull();
    }
    const adverse = rowOf("上下動比");
    expect(screen.getByText("上下動比")).toHaveClass("text-status-warn");
    expect(
      within(adverse).getByText(/範囲外（高い側）/),
    ).toHaveClass("text-status-warn");
  });

  it("test_signal_row_low_side_for_cadence", () => {
    renderRows([
      signal({
        metric: "cadence",
        label_ja: "ケイデンス",
        unit: "spm",
        today: 168,
        normal_low: 169,
        normal_high: 176,
        status: "edge",
        z: 1.1,
      }),
    ]);

    // Cadence is worse when low, so the same positive (unfavourable) z names
    // the other end of the band than it would for ground contact time.
    expect(rowOf("ケイデンス")).toHaveTextContent("低い側の端");
  });

  it("test_signal_note_rendered_under_adverse_row", () => {
    renderRows(
      [
        signal({
          metric: "gct",
          label_ja: "接地時間",
          status: "outside",
          adverse: true,
          z: 2.2,
          today: 268,
        }),
        signal({ metric: "vo", label_ja: "上下動", status: "within" }),
      ],
      [
        { signal: "gct", text: "終盤の上りでピッチが落ちた分が出ています。" },
        { signal: "vo", text: "これは範囲内なので気にしなくて大丈夫です。" },
      ],
    );

    // The reason sits with the reading it explains, not in a block of its own.
    expect(rowOf("接地時間")).toHaveTextContent(
      "終盤の上りでピッチが落ちた分が出ています。",
    );
    // A note for a within-range signal is not shown at all: it would read as
    // a warning about something the page just called normal.
    expect(
      screen.queryByText("これは範囲内なので気にしなくて大丈夫です。"),
    ).not.toBeInTheDocument();
  });

  it("test_normal_range_row_has_band_and_dot", () => {
    renderRows([
      signal({ metric: "gct", label_ja: "接地時間", status: "within", z: 0.58 }),
    ]);

    const row = rowOf("接地時間");
    // The usual range is drawn, not just described: the track spans ±3σ and
    // the band is the ±2σ inside it, so the dot lands somewhere meaningful.
    const band = row.querySelector<HTMLElement>('[data-part="band"]');
    expect(band).not.toBeNull();
    expect(band?.style.left).toBe("16.67%");
    expect(band?.style.width).toBe("66.67%");

    // One mark at the reading, not a bar growing from the centre (#1270).
    const dot = row.querySelector<HTMLElement>('[data-part="dot"]');
    expect(dot).not.toBeNull();
    expect(parseFloat(dot?.style.left ?? "")).toBeCloseTo(59.7, 1);
    expect(dot?.className).toContain("h-2.5");
    expect(dot?.className).toContain("w-2.5");
    expect(dot?.className).toContain("bg-ink");
  });

  it("test_normal_range_adverse_dot_is_warn", () => {
    renderRows([
      signal({
        metric: "vr",
        label_ja: "上下動比",
        status: "outside",
        adverse: true,
        z: 2.4,
      }),
      signal({
        family: "cardio",
        metric: "hr_vs_expected",
        label_ja: "心拍（想定比）",
        unit: "bpm",
        status: "outside",
        adverse: false,
        z: -2.1,
      }),
    ]);

    const adverse = rowOf("上下動比").querySelector<HTMLElement>(
      '[data-part="dot"]',
    );
    expect(adverse?.className).toContain("bg-status-warn");

    // A favourable outlier sits on the good side and takes no colour: tinting
    // it would teach the reader to ignore the tint.
    const favourable = rowOf("心拍（想定比）").querySelector<HTMLElement>(
      '[data-part="dot"]',
    );
    expect(favourable?.className).toContain("bg-ink");
    expect(favourable?.className).not.toContain("bg-status-warn");
    expect(parseFloat(favourable?.style.left ?? "")).toBeCloseTo(15, 1);
  });

  it("test_normal_range_axis_caption_present", () => {
    renderRows(SIGNALS);

    // Named once, above the first track — the figure has to say which side is
    // the unfavourable one on its own.
    for (const caption of ["← 良い側", "いつもの範囲", "悪い側 →"]) {
      expect(screen.getAllByText(caption)).toHaveLength(1);
    }
  });

  it("test_normal_range_insufficient_has_no_dot", () => {
    renderRows(SIGNALS);

    // Nothing to place and no range to place it in: the track keeps its centre
    // line and the row says why in words.
    const row = rowOf("心拍ドリフト");
    expect(row.querySelector('[data-part="dot"]')).toBeNull();
    expect(row.querySelector('[data-part="band"]')).toBeNull();
    expect(row.querySelector('[data-part="track"]')).not.toBeNull();
  });

  it("shows the zone split and the way to the long view", () => {
    renderRows(SIGNALS);

    expect(screen.getByRole("img", { name: "心拍ゾーン分布" })).toBeInTheDocument();
    expect(screen.getByText("Z2 75%")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /長期の推移/ })).toHaveAttribute(
      "href",
      "/performance",
    );
  });
});
