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
