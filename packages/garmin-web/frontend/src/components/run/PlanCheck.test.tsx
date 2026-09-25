import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PlanCheck, { formatOverTime, outcomeText } from "./PlanCheck";
import type { PlanCheckRow, RunPlan, RunPurpose } from "../../types";

const PLAN: RunPlan = {
  verdict: "🟡",
  title: "ロング 22km",
  checks: [
    {
      axis: "intensity",
      target: "long_run",
      actual: "long_run",
      status: "on_plan",
      on_plan: true,
    },
    {
      axis: "volume",
      target: "22.0km",
      actual: "22.14km",
      status: "on_plan",
      on_plan: true,
    },
    {
      axis: "hr_ceiling",
      target: "≦150bpm",
      actual: "148bpm",
      status: "off_plan",
      on_plan: false,
    },
  ],
  hr_ceiling: { bpm: 150, seconds_over: 321, pct_over: 12.4 },
};

describe("PlanCheck", () => {
  it("test_plan_check_hidden_without_plan", () => {
    const { container } = render(<PlanCheck plan={null} />);

    // A day with no prescription has nothing to check against: the block is
    // absent rather than empty.
    expect(screen.queryByText("計画との照合")).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it("shows purpose without a plan", () => {
    // An unprescribed run still has an inferred purpose and a judged share,
    // and that is where "（推定）" matters most (#1326).
    render(
      <PlanCheck
        plan={null}
        purpose={{ id: "easy", label_ja: "イージー", source: "inferred" }}
        judgedShare={{ hr: 0.9, form: 0.95 }}
      />,
    );

    expect(screen.getByText("計画との照合")).toBeInTheDocument();
    expect(screen.getByText("処方なし")).toBeInTheDocument();
    expect(screen.getByTestId("plan-purpose")).toHaveTextContent("イージー（推定）");
    expect(screen.getByTestId("plan-judged-share")).toHaveTextContent("心拍 90%");
    // No check grid without a plan.
    expect(screen.queryByText("強度")).not.toBeInTheDocument();
  });

  it("test_plan_check_is_a_grid_with_status_in_each_row", () => {
    const { container } = render(<PlanCheck plan={PLAN} />);

    // A table pushed the 状態 column — the answer the reader came for — off a
    // 400px screen, so the card is a grid whose rows stack instead (#1252).
    expect(container.querySelector("table")).toBeNull();

    const rows = screen.getAllByRole("group");
    expect(rows.map((row) => row.getAttribute("aria-label"))).toEqual([
      "強度",
      "量",
      "心拍上限",
    ]);
    expect(within(rows[0]).getByText("計画どおり")).toBeInTheDocument();
    expect(within(rows[1]).getByText("計画どおり")).toBeInTheDocument();

    const ceilingRow = rows[2];
    const flag = within(ceilingRow).getByText("ずれ");
    expect(flag).toHaveClass("text-status-warn");
    // The over-ceiling bar reads as part of what actually happened, so it
    // belongs to the 実績 cell rather than to a column of its own.
    const actualCell = within(ceilingRow).getByText("148bpm")
      .parentElement as HTMLElement;
    expect(actualCell).toHaveTextContent("実績");
    expect(within(actualCell).getByText(/超過 5:21/)).toBeInTheDocument();
  });

  it("test_plan_check_header_and_rows_share_one_grid", () => {
    render(<PlanCheck plan={PLAN} />);

    const rows = screen.getAllByRole("group");
    const header = screen.getByText("状態").parentElement as HTMLElement;
    const grid = header.parentElement as HTMLElement;

    // One grid for the whole block: the header cells and every row's cells are
    // `display: contents` inside it, so the four tracks are measured once. Per
    // row grids sized their own columns and put 計画どおり under 目標 (#1270).
    expect(rows.every((row) => row.parentElement === grid)).toBe(true);
    expect(grid.className).toContain(
      "md:grid-cols-[96px_minmax(0,1fr)_minmax(0,1.5fr)_72px]",
    );
    expect(header.className).toContain("md:contents");
    for (const row of rows) {
      expect(row.className).toContain("md:contents");
      // No row may re-declare tracks of its own at `md`+.
      expect(row.className).not.toMatch(/md:grid-cols-/);
    }

    // The status cell is last in the DOM, so the shared grid drops it into the
    // 状態 column without an explicit column start.
    const cells = Array.from(rows[0].children);
    expect(cells).toHaveLength(4);
    expect(cells[3]).toHaveTextContent("計画どおり");
  });

  it("test_plan_check_stacked_layout_unchanged_below_md", () => {
    render(<PlanCheck plan={PLAN} />);

    const rows = screen.getAllByRole("group");
    // Below `md` the row is its own two-column grid and the tag is ordered up
    // onto the name's line — that is what keeps it on a 400px screen.
    for (const row of rows) {
      expect(row.className).toContain("grid-cols-[minmax(0,1fr)_auto]");
    }
    const tagCell = within(rows[2]).getByText("ずれ").parentElement as HTMLElement;
    expect(tagCell.className).toContain("order-2");
    expect(tagCell.className).toContain("justify-self-end");
    // The name keeps the first slot, the two readings follow it.
    expect(
      (within(rows[2]).getByText("心拍上限") as HTMLElement).className,
    ).toContain("order-1");
    expect(
      (within(rows[2]).getByText("≦150bpm").parentElement as HTMLElement)
        .className,
    ).toContain("order-3");
  });

  it("states a run that never touched the cap", () => {
    render(
      <PlanCheck
        plan={{
          ...PLAN,
          hr_ceiling: { bpm: 150, seconds_over: 0, pct_over: 0 },
        }}
      />,
    );

    expect(screen.getByText("超過なし")).toBeInTheDocument();
  });

  it("renders strides axis label", () => {
    render(
      <PlanCheck
        plan={{
          ...PLAN,
          checks: [
            ...PLAN.checks,
            {
              axis: "strides",
              target: "4本",
              actual: "4本",
              status: "on_plan",
              on_plan: true,
            },
          ],
        }}
      />,
    );

    const row = screen.getByRole("group", { name: "流し" });
    expect(within(row).getByText("流し")).toBeInTheDocument();
    expect(within(row).getAllByText("4本")).toHaveLength(2);
    // Only the ceiling row carries the over-ceiling bar: stride HR peaks are
    // not an excursion.
    expect(within(row).queryByText(/超過/)).toBeNull();
  });

  it("keeps the ceiling bar for hr_ceiling", () => {
    // Structure-derived rows (#1404) still get the bar on the ceiling row.
    render(
      <PlanCheck
        plan={{
          ...PLAN,
          checks: [
            {
              axis: "hr_ceiling",
              label_ja: "心拍上限",
              target: "150 bpm 以下",
              actual: "超過 5:21（12.4%）",
              status: "off_plan",
              on_plan: false,
              segments: [],
            },
          ],
        }}
      />,
    );

    const row = screen.getByRole("group", { name: "心拍上限" });
    expect(within(row).getByText(/超過 5:21\s*（\s*12.4%）/, {
      selector: "span.text-status-warn",
    })).toBeInTheDocument();
    // hr_ceiling carries no step list.
    expect(within(row).queryByRole("list")).toBeNull();
  });

  it("test_format_over_time_reads_as_a_length", () => {
    // A length of time, not a clock reading: "00:02" looks like a timestamp.
    expect(formatOverTime(321)).toBe("5:21");
    expect(formatOverTime(2)).toBe("0:02");
    expect(formatOverTime(3849)).toBe("1:04:09");
  });
});

const LONG: RunPurpose = {
  id: "long_easy",
  label_ja: "ロング（有酸素）",
  source: "prescription",
};

describe("outcomeText (#1348)", () => {
  it("test_outcome_text_met", () => {
    expect(
      outcomeText({
        ...LONG,
        outcome: {
          met: true,
          sustained_share: 0.97,
          breakdown_from_km: null,
          reason: "held",
        },
      }),
    ).toBe("達成");
  });

  it("test_outcome_text_breakdown", () => {
    const missed = (km: number) => ({
      ...LONG,
      outcome: {
        met: false,
        sustained_share: 0.62,
        breakdown_from_km: km,
        reason: "came apart",
      },
    });
    expect(outcomeText(missed(18))).toBe("達成できず（18 km から崩れ）");
    expect(outcomeText(missed(18.5))).toBe("達成できず（18.5 km から崩れ）");
  });

  it("test_outcome_text_absent", () => {
    // Not judged -- intervals, recovery, a build older than #1340 -- says
    // nothing rather than implying the run was fine.
    expect(outcomeText({ ...LONG, outcome: null })).toBeNull();
    expect(outcomeText(LONG)).toBeNull();
    expect(outcomeText(null)).toBeNull();
    expect(
      outcomeText({
        id: "unknown",
        label_ja: "",
        source: "default",
        outcome: {
          met: true,
          sustained_share: 1,
          breakdown_from_km: null,
          reason: "held",
        },
      }),
    ).toBeNull();
  });

  it("test_plan_check_renders_outcome", () => {
    // Unprescribed: the outcome line is the only place the answer lives.
    const { unmount } = render(
      <PlanCheck
        plan={null}
        purpose={{
          ...LONG,
          source: "inferred",
          outcome: {
            met: false,
            sustained_share: 0.62,
            breakdown_from_km: 18,
            reason: "came apart",
          },
        }}
      />,
    );
    const item = screen.getByTestId("plan-outcome");
    expect(item).toHaveTextContent("目的の達成");
    const value = within(item).getByText("達成できず（18 km から崩れ）");
    expect(value).toHaveClass("text-status-warn");
    unmount();

    // No outcome, no item.
    render(<PlanCheck plan={null} purpose={{ ...LONG, source: "inferred" }} />);
    expect(screen.queryByTestId("plan-outcome")).toBeNull();
  });

  it("test_plan_check_meta_values_share_one_column", () => {
    // The labels differ in length, so each row sized off its own label
    // started its value at a different x (#1350). One shared grid aligns them.
    render(
      <PlanCheck
        plan={null}
        purpose={{
          ...LONG,
          source: "inferred",
          outcome: {
            met: true,
            sustained_share: 0.97,
            breakdown_from_km: null,
            reason: "held",
          },
        }}
        judgedShare={{ hr: 0.92, form: 0.96 }}
      />,
    );
    const items = ["plan-purpose", "plan-outcome", "plan-judged-share"].map(
      (id) => screen.getByTestId(id),
    );
    const list = items[0].parentElement;
    expect(list?.tagName).toBe("DL");
    expect(list).toHaveClass("grid", "grid-cols-[auto_minmax(0,1fr)]");
    for (const item of items) {
      expect(item.parentElement).toBe(list);
      expect(item).toHaveClass("contents");
    }
  });
});

/** PLAN with the purpose axis (#1353): the long run came apart at 18 km. */
const PLAN_WITH_CONTINUITY: RunPlan = {
  ...PLAN,
  checks: [
    ...PLAN.checks,
    {
      axis: "continuity",
      target: "最後まで走り続ける",
      actual: "18 km から崩れ",
      status: "off_plan",
      on_plan: false,
    },
  ],
};

describe("purpose display by prescribed / unprescribed (#1354)", () => {
  it("test_plan_check_prescribed_hides_outcome_line", () => {
    render(
      <PlanCheck
        plan={PLAN_WITH_CONTINUITY}
        purpose={{
          ...LONG,
          outcome: {
            met: false,
            sustained_share: 0.62,
            breakdown_from_km: 18,
            reason: "came apart",
          },
        }}
      />,
    );

    // The table's 継続 row answers it; no second line above the table.
    expect(screen.queryByTestId("plan-outcome")).toBeNull();
    expect(screen.getByTestId("plan-purpose")).toHaveTextContent(
      "ロング（有酸素）",
    );
    const row = screen.getByRole("group", { name: "継続" });
    expect(within(row).getByText("18 km から崩れ")).toBeInTheDocument();
    expect(within(row).getByText("ずれ")).toBeInTheDocument();
  });

  it("test_plan_check_unprescribed_keeps_outcome_line", () => {
    render(
      <PlanCheck
        plan={null}
        purpose={{
          ...LONG,
          source: "inferred",
          outcome: {
            met: true,
            sustained_share: 0.97,
            breakdown_from_km: null,
            reason: "held",
          },
        }}
      />,
    );

    expect(screen.getByTestId("plan-outcome")).toHaveTextContent("達成");
  });

  it("test_plan_check_continuity_axis_label", () => {
    render(<PlanCheck plan={PLAN_WITH_CONTINUITY} />);

    const row = screen.getByRole("group", { name: "継続" });
    expect(within(row).getByText("継続")).toBeInTheDocument();
    expect(within(row).getByText("最後まで走り続ける")).toBeInTheDocument();
  });
});

/** A five-stage build-up, every stage in its band (#1404). */
const STAGES_ROW: PlanCheckRow = {
  axis: "stages",
  label_ja: "段階的ビルドアップ",
  target: "130-140 → 140-150 → 150-160 → 160-170 → 170-180 bpm",
  actual: "135 → 146 → 155 → 165 → 174 bpm",
  status: "on_plan",
  on_plan: true,
  verdict: "✅",
  segments: [
    ["第1段", "130-140 bpm", "135 bpm"],
    ["第2段", "140-150 bpm", "146 bpm"],
    ["第3段", "150-160 bpm", "155 bpm"],
    ["第4段", "160-170 bpm", "165 bpm"],
    ["第5段", "170-180 bpm", "174 bpm"],
  ].map(([label, target, actual], index) => ({
    segment_id: String(index + 1),
    label,
    target,
    actual,
    on_plan: true,
  })),
};

describe("structure-derived axes (#1407)", () => {
  it("renders label_ja for a dynamic axis", () => {
    // No AXIS_LABELS entry exists for hr_band_2: the row names itself.
    render(
      <PlanCheck
        plan={{
          ...PLAN,
          checks: [
            {
              axis: "hr_band_2",
              label_ja: "心拍の帯（2本目）",
              target: "150-160 bpm",
              actual: "帯内 72%（上 8%）",
              status: "on_plan",
              on_plan: true,
            },
          ],
        }}
      />,
    );

    const row = screen.getByRole("group", { name: "心拍の帯（2本目）" });
    expect(within(row).getByText("心拍の帯（2本目）")).toBeInTheDocument();
    expect(screen.queryByText("hr_band_2")).toBeNull();
  });

  it("renders stage rows", () => {
    render(<PlanCheck plan={{ ...PLAN, checks: [STAGES_ROW] }} />);

    const row = screen.getByRole("group", { name: "段階的ビルドアップ" });
    const list = within(row).getByRole("list", {
      name: "段階的ビルドアップの内訳",
    });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(5);
    expect(items[0]).toHaveTextContent("第1段");
    expect(items[0]).toHaveTextContent("130-140 bpm");
    expect(items[0]).toHaveTextContent("135 bpm");
    expect(items[4]).toHaveTextContent("170-180 bpm");
    expect(items[4]).toHaveTextContent("174 bpm");
    for (const item of items) {
      expect(item).toHaveTextContent("✅");
      expect(item).not.toHaveTextContent("🟡");
    }
  });

  it("marks an off-band step with 🟡 on reps and hr_band rows", () => {
    render(
      <PlanCheck
        plan={{
          ...PLAN,
          checks: [
            {
              axis: "reps",
              label_ja: "本数",
              target: "2本 × 1000m",
              actual: "1/2本",
              status: "short",
              on_plan: false,
              segments: [
                {
                  segment_id: "2#1",
                  label: "メイン 1本目",
                  target: "1000m",
                  actual: "3:50（3:50/km）",
                  on_plan: true,
                },
                {
                  segment_id: "2#2",
                  label: "メイン 2本目",
                  target: "1000m",
                  actual: "2:10（4:20/km）",
                  on_plan: false,
                },
              ],
            },
          ],
        }}
      />,
    );

    const row = screen.getByRole("group", { name: "本数" });
    const items = within(row).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("✅");
    expect(items[1]).toHaveTextContent("🟡");
    expect(within(row).getByText("不足")).toHaveClass("text-status-warn");
  });

  it("renders insufficient as neutral", () => {
    render(
      <PlanCheck
        plan={{
          ...PLAN,
          checks: [
            {
              axis: "hr_band",
              label_ja: "心拍帯",
              target: "150-160 bpm",
              actual: "-",
              status: "insufficient",
              on_plan: false,
              segments: [],
            },
          ],
        }}
      />,
    );

    const row = screen.getByRole("group", { name: "心拍帯" });
    const tag = within(row).getByText("判定不能");
    expect(tag).toHaveClass("text-ink-muted");
    expect(tag).not.toHaveClass("text-status-warn");
    expect(within(row).queryByText("ずれ")).toBeNull();
    expect(row).not.toHaveTextContent("✅");
    expect(row).not.toHaveTextContent("🟡");
  });
});
