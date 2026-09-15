import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import EfficiencyBlock, { efficiencySummaryLine } from "./EfficiencyBlock";
import { ZONE_COLORS } from "../../components/chartTheme";
import type { EfficiencyTrendPoint } from "../../api/trends";

// echarts needs a real canvas; mock the modular wrapper out for jsdom.
vi.mock("../../lib/echarts", () => ({
  echarts: {
    init: () => ({
      setOption: vi.fn(),
      resize: vi.fn(),
      dispose: vi.fn(),
    }),
  },
}));

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

  it("renders an empty state without crashing", () => {
    render(<EfficiencyBlock data={[]} />);

    expect(screen.getByText("データがありません")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "HRゾーン分布" })).toBeNull();
  });
});
