import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RunFlow, { SCENE_TINTS } from "./RunFlow";
import { THRESHOLD_LINE } from "../chartTheme";
import type { RunMoment, SplitRow } from "../../types";

// The chart's canvas says nothing in jsdom; what matters is the option the
// component hands the renderer (same approach as chartSemantics.test.tsx).
const captured = vi.hoisted(() => ({ options: [] as ChartOption[] }));

vi.mock("../EChart", () => ({
  default: (props: { option: unknown }) => {
    captured.options.push(props.option as ChartOption);
    return null;
  },
}));

type MarkItem = {
  xAxis?: string;
  yAxis?: number;
  itemStyle?: { color?: string };
  lineStyle?: { color?: string; type?: string };
};
type Series = {
  name?: string;
  markArea?: { data?: MarkItem[][] };
  markLine?: { data?: MarkItem[] };
};
type ChartOption = {
  grid?: unknown[];
  series?: Series[];
};

function split(index: number, pace: number, hr: number): SplitRow {
  return {
    activity_id: 123,
    split_index: index,
    distance: 1.0,
    duration_seconds: pace,
    pace_seconds_per_km: pace,
    heart_rate: hr,
    cadence: 168,
    power: 250,
    max_heart_rate: hr + 6,
  };
}

const SPLITS = [
  split(1, 400, 132),
  split(2, 386, 141),
  split(3, 380, 146),
  split(4, 372, 152),
  split(5, 360, 155),
];

function moment(id: string, kind: string, from: number, to: number): RunMoment {
  return { id, kind, km_from: from, km_to: to, facts: {} };
}

const MOMENTS = [
  moment("m1", "start", 1, 1),
  moment("m2", "climb", 2, 2),
  moment("m3", "surge", 4, 4),
  moment("m4", "strong_finish", 5, 5),
];

const TIMELINE = [
  { moment_id: "m1", text: "抑えて入れました。" },
  { moment_id: "m2", text: "上りで心拍が上がりました。" },
  { moment_id: "m3", text: "4kmでペースを上げました。" },
  { moment_id: "m4", text: "最後まで粘りました。" },
];

function renderFlow(moments = MOMENTS, timeline = TIMELINE) {
  captured.options.length = 0;
  render(
    <RunFlow
      splits={SPLITS}
      moments={moments}
      timeline={timeline}
      hrCeiling={150}
    />,
  );
  return captured.options[0];
}

describe("RunFlow", () => {
  it("test_run_flow_lists_scenes_with_text", () => {
    renderFlow();

    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(4);
    const ranges = ["1 km", "2 km", "4 km", "5 km"];
    rows.forEach((row, index) => {
      expect(row).toHaveTextContent(ranges[index]);
      expect(row).toHaveTextContent(TIMELINE[index].text);
    });
  });

  it("keeps a scene the coach did not write about", () => {
    renderFlow(MOMENTS, [TIMELINE[0]]);

    // The run happened whether or not there was anything to say about it: the
    // kilometres stay, named by what the detector saw.
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(4);
    expect(rows[1]).toHaveTextContent("2 km");
    expect(rows[1]).toHaveTextContent("登り");
  });

  it("test_run_flow_uses_stacked_panels_and_mark_areas", () => {
    const option = renderFlow();

    // Pace and heart rate share no unit, so they get a panel each on one km
    // axis rather than two lines crossing on dual axes.
    expect(option.grid).toHaveLength(2);

    const hrSeries = option.series?.find((series) => series.name === "心拍");
    const ceiling = hrSeries?.markLine?.data?.find(
      (item) => item.yAxis === 150,
    );
    expect(ceiling?.lineStyle?.type).toBe("dotted");
    expect(ceiling?.lineStyle?.color).toBe(THRESHOLD_LINE.warn);

    const paceSeries = option.series?.find((series) => series.name === "ペース");
    const areas = paceSeries?.markArea?.data ?? [];
    expect(areas).toHaveLength(4);
    // Adjacent scenes must stay countable: the washes alternate, and each
    // band starts on a hairline.
    expect(areas.map((range) => range[0].itemStyle?.color)).toEqual([
      SCENE_TINTS[0],
      SCENE_TINTS[1],
      SCENE_TINTS[0],
      SCENE_TINTS[1],
    ]);
    expect(paceSeries?.markLine?.data).toHaveLength(4);
  });

  it("draws no ceiling on a day without a prescription", () => {
    captured.options.length = 0;
    render(
      <RunFlow
        splits={SPLITS}
        moments={MOMENTS}
        timeline={TIMELINE}
        hrCeiling={null}
      />,
    );

    const hrSeries = captured.options[0].series?.find(
      (series) => series.name === "心拍",
    );
    expect(
      hrSeries?.markLine?.data?.some((item) => item.yAxis != null),
    ).toBe(false);
  });
});
