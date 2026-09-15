import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import EfficiencyBlock, { efficiencySummaryLine } from "./EfficiencyBlock";
import { ZONE_COLORS } from "../../components/chartTheme";
import type { EfficiencyTrendPoint } from "../../api/trends";

// echarts needs a real canvas; swap the wrapper for a collector so the tests
// can also read the option the block builds.
const captured = vi.hoisted(() => ({ options: [] as ChartOption[] }));

vi.mock("../../components/EChart", () => ({
  default: (props: { option: unknown }) => {
    captured.options.push(props.option as ChartOption);
    return null;
  },
}));

type ChartOption = {
  xAxis?: { data?: string[] };
  series?: { name?: string; stack?: string; data?: (number | null)[] }[];
};

const DATA: EfficiencyTrendPoint[] = [
  {
    date: "2026-06-22",
    aerobic_efficiency: "fair",
    primary_zone: "Zone 3",
    zone1_percentage: 5,
    zone2_percentage: 35,
    zone3_percentage: 40,
    zone4_percentage: 15,
    zone5_percentage: 5,
  },
  {
    date: "2026-06-29",
    aerobic_efficiency: "good",
    primary_zone: "Zone 2",
    zone1_percentage: 10,
    zone2_percentage: 60,
    zone3_percentage: 20,
    zone4_percentage: 8,
    zone5_percentage: 2,
  },
];

/** jsdom reports inline colors as `rgb(r, g, b)`. */
function rgb(hex: string): string {
  const [, r, g, b] = /^#(..)(..)(..)$/.exec(hex)!;
  return `rgb(${parseInt(r, 16)}, ${parseInt(g, 16)}, ${parseInt(b, 16)})`;
}

describe("EfficiencyBlock", () => {
  it("test_efficiency_block_zone_bars", () => {
    const { container } = render(<EfficiencyBlock data={DATA} />);

    const list = screen.getByRole("list", { name: "HRゾーン分布" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(5);

    // The bars show the latest run's split, in zone order and zone colors.
    const shares = [10, 60, 20, 8, 2];
    shares.forEach((share, index) => {
      const bar = container.querySelector<HTMLElement>(
        `[data-zone="${index + 1}"]`,
      );
      expect(bar?.style.width).toBe(`${share}%`);
      expect(bar?.style.backgroundColor).toBe(rgb(ZONE_COLORS[index]));
      expect(within(rows[index]).getByText(`${share}%`)).toBeInTheDocument();
    });
  });

  it("test_efficiency_summary_line", () => {
    // Zones 1-2 are added up for the reader: that sum is what an easy week is
    // judged by.
    expect(efficiencySummaryLine(DATA)).toBe(
      "最新 2026-06-29 · 主ゾーン Zone 2 · 低強度 70%",
    );
    expect(efficiencySummaryLine([])).toBe("");
  });

  it("test_efficiency_block_monthly_bars", () => {
    // 30 runs spread over 14 months: the chart keeps the trailing 12 as one
    // averaged bar each, instead of drawing 30 unreadable columns (#1149).
    const data: EfficiencyTrendPoint[] = [];
    for (let back = 13; back >= 0; back -= 1) {
      const month = new Date(Date.UTC(2026, 8 - back, 1));
      const key = `${month.getUTCFullYear()}-${String(
        month.getUTCMonth() + 1,
      ).padStart(2, "0")}`;
      const runs = back < 2 ? 3 : 2;
      for (let day = 1; day <= runs; day += 1) {
        data.push({
          date: `${key}-0${day}`,
          aerobic_efficiency: "good",
          primary_zone: "Zone 2",
          zone1_percentage: 10,
          zone2_percentage: 60,
          zone3_percentage: 20,
          zone4_percentage: 8,
          zone5_percentage: 2,
        });
      }
    }
    expect(data).toHaveLength(30);

    render(<EfficiencyBlock data={data} today="2026-09-15" />);

    const option = captured.options[captured.options.length - 1];
    expect(option.xAxis?.data).toHaveLength(12);
    expect(option.xAxis?.data?.[0]).toBe("2025-10");
    expect(option.xAxis?.data?.[11]).toBe("2026-09");
    // Five stacked zone series, each with one value per month.
    expect(option.series).toHaveLength(5);
    expect(option.series?.[1].data).toEqual(Array(12).fill(60));
    expect(option.series?.every((s) => s.stack === "zones")).toBe(true);
  });

  it("renders an empty state without crashing", () => {
    render(<EfficiencyBlock data={[]} />);

    expect(screen.getByText("データがありません")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "HRゾーン分布" })).toBeNull();
  });
});
