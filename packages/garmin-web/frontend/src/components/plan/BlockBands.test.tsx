import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { TrainingBlock } from "../../types";
import { weekRowsForMonth } from "../../utils/week";
import BlockBands, { bandSpan } from "./BlockBands";

/** The 35 days a September 2026 grid shows: 08/31 .. 10/04. */
const DAYS = weekRowsForMonth("2026-09", 0).flatMap((row) => row.days);

function block(overrides: Partial<TrainingBlock> = {}): TrainingBlock {
  return {
    block_id: 2,
    phase: "build",
    title: "新潟マラソン ビルド",
    start_date: "2026-08-24",
    end_date: "2026-10-11",
    weight_mode: "微減",
    quality_sessions_per_week: 2,
    ...overrides,
  };
}

describe("bandSpan", () => {
  it("test_band_span_clips_to_month", () => {
    // A block that started in August and ends in October fills the view.
    expect(bandSpan(block(), DAYS)).toEqual({ start: 1, span: 35 });

    // A taper starting mid-view begins on its own day (08/31 is column 1, so
    // 09/28 is column 29) and runs to the last day on screen.
    expect(
      bandSpan(
        block({ phase: "taper", start_date: "2026-09-28" }),
        DAYS,
      ),
    ).toEqual({ start: 29, span: 7 });

    // A block that ended before the view starts is not drawn at all.
    expect(
      bandSpan(
        block({ start_date: "2026-06-01", end_date: "2026-07-31" }),
        DAYS,
      ),
    ).toBeNull();
  });

  it("treats an open-ended block as covering that side of the view", () => {
    expect(bandSpan(block({ start_date: null }), DAYS)).toEqual({
      start: 1,
      span: 35,
    });
    expect(bandSpan(block(), [])).toBeNull();
  });
});

describe("BlockBands", () => {
  it("states the phase, span and budget of each visible block", () => {
    render(<BlockBands blocks={[block()]} days={DAYS} />);

    const band = screen.getByText(/新潟マラソン ビルド/);
    expect(band.textContent).toBe(
      "ビルド · 新潟マラソン ビルド · 08/24 – 10/11 · ポイント練 週2 · 体重 微減",
    );
    // A building phase is the page's one filled band.
    expect(band.className).toContain("bg-ink");
  });

  it("tints an easing phase and renders nothing when no block is visible", () => {
    const { rerender } = render(
      <BlockBands
        blocks={[block({ phase: "cutback", title: "カットバック" })]}
        days={DAYS}
      />,
    );
    expect(screen.getByText(/カットバック/).className).toContain(
      "bg-warn-tint",
    );

    rerender(
      <BlockBands
        blocks={[block({ start_date: "2026-01-01", end_date: "2026-02-01" })]}
        days={DAYS}
      />,
    );
    expect(screen.queryByRole("list")).toBeNull();
  });
});
