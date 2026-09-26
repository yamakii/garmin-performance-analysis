import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import EnergyBalancePanel, {
  buildEnergyBalanceOption,
} from "./EnergyBalancePanel";
import {
  BASELINE_BAND_COLOR,
  COMPARE_COLOR,
  INK_COLOR,
  THRESHOLD_LINE,
} from "../../components/chartTheme";
import { energyBalanceFixture } from "../../test/energyBalanceFixture";

// echarts requires a real canvas; the panel tests only read the DOM around it.
vi.mock("../../lib/echarts", () => ({
  echarts: {
    init: () => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() }),
  },
}));

/** The slice of the option this chart's contract covers. */
interface BarOption {
  xAxis: {
    data: string[];
    axisLabel: { formatter: (value: string) => string };
  };
  series: {
    data: (number | null)[];
    itemStyle: { color: string; borderRadius: number };
    markArea?: {
      itemStyle: { color: string };
      data: [{ yAxis: number }, { yAxis: number }][];
    };
    markLine?: { lineStyle: { color: string }; data: { yAxis: number }[] };
  }[];
}

function optionOf(data = energyBalanceFixture()): BarOption {
  return buildEnergyBalanceOption(data) as unknown as BarOption;
}

describe("buildEnergyBalanceOption", () => {
  it("draws the window days as square ink bars, today left out", () => {
    const option = optionOf();
    expect(option.xAxis.data).toHaveLength(7);
    expect(option.xAxis.data).not.toContain("2026-09-26");
    const [bars] = option.series;
    expect(bars.itemStyle).toEqual({ color: INK_COLOR, borderRadius: 0 });
    expect(bars.data[0]).toBe(-1173);
  });

  it("buildEnergyBalanceOption draws excluded days as null with the reason", () => {
    const base = energyBalanceFixture();
    const days = base.days.map((day) =>
      day.date === "2026-09-22"
        ? { ...day, used: false, intake_status: "not_logged" }
        : day,
    );
    const option = optionOf(
      energyBalanceFixture({
        days,
        window: {
          paired_days: 6,
          excluded: [{ date: "2026-09-22", reason: "not_logged" }],
        },
      }),
    );

    const index = option.xAxis.data.indexOf("2026-09-22");
    expect(option.series[0].data[index]).toBeNull();
    expect(option.series[0].data[index]).not.toBe(0);
    expect(option.xAxis.axisLabel.formatter("2026-09-22")).toBe(
      "09/22\n記録なし",
    );
    expect(option.xAxis.axisLabel.formatter("2026-09-21")).toBe("09/21");
  });

  it("buildEnergyBalanceOption band and mean line", () => {
    const deeper = optionOf().series[0];
    expect(deeper.markArea?.itemStyle.color).toBe(BASELINE_BAND_COLOR);
    expect(deeper.markArea?.data).toEqual([[{ yAxis: -150 }, { yAxis: 150 }]]);
    expect(deeper.markLine?.lineStyle.color).toBe(THRESHOLD_LINE.warn);
    expect(deeper.markLine?.data).toEqual([{ yAxis: -469 }]);

    const within = optionOf(
      energyBalanceFixture({
        window: { mean_balance_kcal: -60 },
        target: { verdict: "within_target" },
      }),
    ).series[0];
    expect(within.markLine?.lineStyle.color).toBe(COMPARE_COLOR);

    const insufficient = optionOf(
      energyBalanceFixture({ window: { status: "insufficient" } }),
    ).series[0];
    expect(insufficient.markLine).toBeUndefined();
    expect(insufficient.markArea).toBeDefined();
  });

  it("omits the band when the block sets none", () => {
    const [bars] = optionOf(
      energyBalanceFixture({ target: { band_kcal: null, verdict: null } }),
    ).series;
    expect(bars.markArea).toBeUndefined();
  });
});

describe("EnergyBalancePanel", () => {
  it("EnergyBalancePanel ok window", () => {
    render(<EnergyBalancePanel data={energyBalanceFixture()} />);

    expect(screen.getByText("平均収支")).toBeInTheDocument();
    expect(screen.getByText("-469")).toBeInTheDocument();
    expect(screen.getByText("1880")).toBeInTheDocument();
    expect(screen.getByText("2350")).toBeInTheDocument();
    expect(screen.getByText("7/7日 · 暫定6日")).toBeInTheDocument();
    expect(screen.getByText("平均 -469 · 目標帯より赤字側")).toBeInTheDocument();
    expect(screen.getByText("目標帯 -150〜+150（維持）")).toBeInTheDocument();
  });

  it("EnergyBalancePanel insufficient window", () => {
    render(
      <EnergyBalancePanel
        data={energyBalanceFixture({
          window: { status: "insufficient", paired_days: 4, required_days: 5 },
        })}
      />,
    );

    expect(screen.queryByText("平均収支")).not.toBeInTheDocument();
    expect(screen.getByText("判定なし · 4/5日")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "日ごとのエネルギー収支グラフ" }),
    ).toBeInTheDocument();
  });

  it("EnergyBalancePanel no_logging", () => {
    const { container } = render(
      <EnergyBalancePanel
        data={energyBalanceFixture({ window: { status: "no_logging" } })}
      />,
    );

    expect(container).toHaveTextContent(/^摂取の記録がありません。$/);
  });

  it("EnergyBalancePanel calibration caption", () => {
    const { unmount } = render(
      <EnergyBalancePanel data={energyBalanceFixture()} />,
    );
    expect(screen.queryByText(/体重の/)).not.toBeInTheDocument();
    unmount();

    render(
      <EnergyBalancePanel
        data={energyBalanceFixture({
          calibration: { status: "logged_deficit_exceeds_weight" },
        })}
      />,
    );
    expect(
      screen.getByText("体重の減りより赤字が大きい（記録漏れの可能性）"),
    ).toBeInTheDocument();
  });
});
