import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RunFlow, {
  CARRIER_SERIES_NAME,
  SCENE_TINTS,
  segmentAt,
  segmentTooltipHtml,
} from "./RunFlow";
import { CHART_FONT_SIZE, METRIC_COLORS, THRESHOLD_LINE } from "../chartTheme";
import { REGISTERED_SERIES_TYPES } from "../../lib/echarts";
import type {
  RunFlowData,
  RunFlowSegment,
  RunFlowStep,
  RunMoment,
} from "../../types";

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
  xAxis?: number;
  yAxis?: number;
  itemStyle?: { color?: string };
  lineStyle?: { color?: string; type?: string };
  label?: { show?: boolean; formatter?: string; position?: string };
};
type Series = {
  name?: string;
  type?: string;
  tooltip?: { show?: boolean };
  data?: [number, number | null][];
  markArea?: { data?: MarkItem[][] };
  markLine?: { data?: MarkItem[] };
};
type Axis = {
  type?: string;
  gridIndex?: number;
  max?: number;
  interval?: number;
  name?: string;
  nameLocation?: string;
};
type Grid = { top?: number; height?: number; right?: number };
type Graphic = {
  top?: number;
  right?: number;
  style?: { text?: string; align?: string; fontSize?: number };
};
type ChartOption = {
  grid?: Grid[];
  xAxis?: Axis[];
  yAxis?: Axis[];
  series?: Series[];
  graphic?: Graphic[];
};

/** One drawn segment: a split of a long step, or a whole short step. */
function segment(
  lap: number,
  km: [number, number],
  seconds: [number, number],
  values: { pace?: number | null; hr?: number | null; max?: number | null },
  stepId = "s1",
): RunFlowSegment {
  return {
    split_from: lap,
    split_to: lap,
    step_id: stepId,
    start_km: km[0],
    end_km: km[1],
    start_s: seconds[0],
    end_s: seconds[1],
    pace_s_per_km: values.pace ?? null,
    avg_hr: values.hr ?? null,
    max_hr: values.max ?? null,
  };
}

function step(
  id: string,
  labels: [string, string],
  laps: [number, number],
  overrides: Partial<RunFlowStep> = {},
): RunFlowStep {
  return {
    id,
    role: "run",
    label_ja: labels[0],
    short_ja: labels[1],
    rep_no: null,
    split_from: laps[0],
    split_to: laps[1],
    start_km: 0,
    end_km: 0,
    start_s: 0,
    end_s: 0,
    distance_km: 0,
    duration_s: 0,
    pace_s_per_km: null,
    avg_hr: null,
    max_hr: null,
    is_long: true,
    ...overrides,
  };
}

function flowOf(
  segments: RunFlowSegment[],
  overrides: Partial<RunFlowData> = {},
): RunFlowData {
  const last = segments[segments.length - 1];
  return {
    axis: "distance",
    total_km: last?.end_km ?? 0,
    total_s: last?.end_s ?? 0,
    segments,
    steps: [step("s1", ["本編", "本編"], [1, segments.length])],
    fragments: { count: 0, distance_km: 0 },
    ...overrides,
  };
}

function moment(
  id: string,
  kind: string,
  laps: [number, number],
  overrides: Partial<RunMoment> = {},
): RunMoment {
  return {
    id,
    kind,
    unit: "km",
    label_ja: `${laps[0]}–${laps[1]} km`,
    step_id: "s1",
    rep_no: null,
    km_from: laps[0] - 1,
    km_to: laps[1],
    t_from_s: (laps[0] - 1) * 400,
    t_to_s: laps[1] * 400,
    split_from: laps[0],
    split_to: laps[1],
    facts: {},
    ...overrides,
  };
}

/** A plain five-kilometre run: one step, one segment per kilometre. */
const STEADY_SEGMENTS = [400, 386, 380, 372, 360].map((pace, index) =>
  segment(
    index + 1,
    [index, index + 1],
    [index * 400, (index + 1) * 400],
    { pace, hr: 132 + index * 6, max: 138 + index * 6 },
  ),
);
const STEADY_FLOW = flowOf(STEADY_SEGMENTS);

const MOMENTS = [
  moment("m1", "start", [1, 1], { label_ja: "1 km" }),
  moment("m2", "climb", [2, 2], { label_ja: "2 km" }),
  moment("m3", "surge", [4, 4], { label_ja: "4 km" }),
  moment("m4", "strong_finish", [5, 5], { label_ja: "5 km" }),
];

const TIMELINE = [
  { moment_id: "m1", text: "抑えて入れました。" },
  { moment_id: "m2", text: "上りで心拍が上がりました。" },
  { moment_id: "m3", text: "4kmでペースを上げました。" },
  { moment_id: "m4", text: "最後まで粘りました。" },
];

function renderFlow(
  flow: RunFlowData = STEADY_FLOW,
  moments: RunMoment[] = MOMENTS,
  timeline = TIMELINE,
  hrCeiling: number | null = 150,
) {
  captured.options.length = 0;
  render(
    <RunFlow
      flow={flow}
      moments={moments}
      timeline={timeline}
      hrCeiling={hrCeiling}
    />,
  );
  return captured.options[0];
}

function seriesNamed(option: ChartOption, name: string): Series | undefined {
  return option.series?.find((series) => series.name === name);
}

/** The x spans of the bands drawn over the plot panels. */
function bandSpans(option: ChartOption): [number, number][] {
  const areas = seriesNamed(option, "ペース")?.markArea?.data ?? [];
  return areas.map((range) => [range[0].xAxis as number, range[1].xAxis as number]);
}

/** The caption written above each band, in band order. */
function bandCaptions(option: ChartOption): string[] {
  const areas = seriesNamed(option, "場面")?.markArea?.data ?? [];
  return areas.map((range) => range[0].label?.formatter ?? "");
}

describe("RunFlow chart axis", () => {
  it("test_run_flow_x_axis_is_distance_for_steady_runs", () => {
    // A 0.6 km manual lap is 0.6 km wide, not one category slot: the segments
    // are drawn as steps over the ground they actually covered (#1269).
    const flow = flowOf([
      segment(1, [0, 1], [0, 400], { pace: 400, hr: 140 }),
      segment(2, [1, 1.6], [400, 640], { pace: 400, hr: 144 }),
      segment(3, [1.6, 2.6], [640, 1040], { pace: 400, hr: 148 }),
    ]);
    flow.segments[1].pace_s_per_km = 380;
    flow.segments[2].pace_s_per_km = 360;

    const option = renderFlow(flow, []);

    expect(option.xAxis).not.toHaveLength(0);
    for (const axis of option.xAxis ?? []) {
      expect(axis.type).toBe("value");
      expect(axis.max).toBe(2.6);
    }
    expect(seriesNamed(option, "ペース")?.data).toEqual([
      [0, 400],
      [1, 400],
      [1, 380],
      [1.6, 380],
      [1.6, 360],
      [2.6, 360],
    ]);
  });

  it("test_run_flow_x_axis_is_minutes_for_rep_sessions", () => {
    // A 120 s rest covers 0.18 km — invisible on a distance axis, two clear
    // minutes on a time axis.
    const segments = [
      segment(1, [0, 2], [0, 600], { pace: 300, hr: 130 }, "s1"),
      segment(2, [2, 3.11], [600, 960], { pace: 324, hr: 170 }, "s2"),
      segment(3, [3.11, 3.29], [960, 1080], { pace: 667, hr: 150 }, "s3"),
      segment(4, [3.29, 4.4], [1080, 1440], { pace: 324, hr: 171 }, "s4"),
      segment(5, [4.4, 6.4], [1440, 2115], { pace: 337, hr: 140 }, "s5"),
    ];
    const option = renderFlow(
      flowOf(segments, { axis: "time", total_km: 6.4, total_s: 2115 }),
      [],
    );

    for (const axis of option.xAxis ?? []) {
      expect(axis.max).toBe(35.25);
    }
    // The rest sits where it happened: minutes 16 to 18.
    const pace = seriesNamed(option, "ペース")?.data ?? [];
    expect(pace[4]).toEqual([16, 667]);
    expect(pace[5]).toEqual([18, 667]);
  });

  it("test_axis_unit_is_not_on_the_tick_row", () => {
    const option = renderFlow();

    // "25" followed by "km" reads as "2km", and at 400 px the two overlap
    // outright: the unit gets a line of its own under the tick labels.
    for (const axis of option.xAxis ?? []) {
      expect(axis.name).toBeUndefined();
    }
    const unit = option.graphic?.[0];
    expect(unit?.style?.text).toBe("km");
    expect(unit?.style?.align).toBe("right");
    const lower = (option.grid ?? [])[2];
    const tickRowBottom =
      (lower.top ?? 0) + (lower.height ?? 0) + CHART_FONT_SIZE;
    expect(unit?.top ?? 0).toBeGreaterThan(tickRowBottom);
  });

  it("test_run_flow_has_no_axis_titles_in_the_caption_row", () => {
    const option = renderFlow();

    // The caption row belongs to the band captions: an axis title placed
    // there met the first caption whenever a scene started at the axis —
    // "ペース①" over "アップ" (#1277). The legend under the chart and the
    // series names carry what the titles said.
    for (const axis of option.yAxis ?? []) {
      expect(axis.name).toBeUndefined();
      expect(axis.nameLocation).toBeUndefined();
    }
  });

  it("states the axis and what a step's width means", () => {
    renderFlow();
    expect(
      screen.getByText(/横軸は実際の距離（km）/),
    ).toHaveTextContent("段の幅 = そのスプリット（区間）が覆った距離");

    renderFlow(flowOf(STEADY_SEGMENTS, { axis: "time", total_s: 2000 }), []);
    expect(screen.getByText(/横軸は経過時間（分）/)).toBeInTheDocument();
  });
});

describe("RunFlow series legend", () => {
  it("test_run_flow_legend_names_the_series", () => {
    renderFlow();

    // The y-axis titles are gone (#1277), so this row is the only thing that
    // says which line is which.
    expect(screen.getByText("ペース /km（上が速い）")).toBeInTheDocument();
    expect(screen.getByText("平均心拍")).toBeInTheDocument();
    expect(screen.getByText("最大心拍")).toBeInTheDocument();
  });

  it("test_run_flow_legend_swatches_use_series_colours", () => {
    const { container } = render(
      <RunFlow flow={STEADY_FLOW} moments={MOMENTS} timeline={TIMELINE} hrCeiling={150} />,
    );

    const pace = container.querySelector<HTMLElement>('[data-series="pace"]');
    const heartRate = container.querySelector<HTMLElement>(
      '[data-series="heart_rate"]',
    );
    // jsdom normalises the inline colour to rgb(); compare through a probe so
    // the test follows METRIC_COLORS instead of pinning a literal.
    const probe = document.createElement("span");
    probe.style.backgroundColor = METRIC_COLORS.speed;
    expect(pace?.style.backgroundColor).toBe(probe.style.backgroundColor);
    probe.style.backgroundColor = METRIC_COLORS.heart_rate;
    expect(heartRate?.style.backgroundColor).toBe(probe.style.backgroundColor);
  });

  it("test_ceiling_is_named_in_the_legend_not_on_the_canvas", () => {
    const { container } = render(
      <RunFlow flow={STEADY_FLOW} moments={MOMENTS} timeline={TIMELINE} hrCeiling={150} />,
    );
    const option = captured.options[captured.options.length - 1];

    // The line stays; its label left the canvas. At the start it met the y
    // axis' tick (#1277), outside the end the scene number (#1269), inside the
    // end the max-HR rings of a run that finished at its ceiling (#1285).
    const ceiling = seriesNamed(option, "心拍")?.markLine?.data?.find(
      (item) => item.yAxis === 150,
    );
    expect(ceiling?.lineStyle?.type).toBe("dotted");
    expect(ceiling?.label?.show).toBe(false);

    const swatch = container.querySelector<HTMLElement>(
      '[data-series="hr_ceiling"]',
    );
    const probe = document.createElement("span");
    probe.style.borderColor = THRESHOLD_LINE.warn;
    expect(swatch?.style.borderColor).toBe(probe.style.borderColor);
    expect(swatch?.parentElement?.textContent).toBe("上限 150");
  });

  it("test_legend_has_no_ceiling_entry_without_a_prescription", () => {
    const { container } = render(
      <RunFlow flow={STEADY_FLOW} moments={MOMENTS} timeline={TIMELINE} hrCeiling={null} />,
    );

    expect(container.querySelector('[data-series="hr_ceiling"]')).toBeNull();
    expect(screen.queryByText(/上限/)).not.toBeInTheDocument();
  });

  it("draws no legend when there is nothing to draw", () => {
    render(<RunFlow flow={null} moments={MOMENTS} timeline={TIMELINE} hrCeiling={null} />);

    expect(screen.queryByText("平均心拍")).not.toBeInTheDocument();
  });
});

describe("RunFlow series", () => {
  it("test_run_flow_series_describe_the_same_segments", () => {
    const option = renderFlow();

    // One fragment rule, applied by the report: the pace line cannot drop a
    // split that the heart-rate line still plots (#1268).
    expect(seriesNamed(option, "ペース")?.data).toHaveLength(10);
    expect(seriesNamed(option, "心拍")?.data).toHaveLength(10);
    expect(seriesNamed(option, "最大心拍")?.data).toHaveLength(5);
    // Nothing else is plotted: 場面 is the caption row, which carries one
    // invisible point so its labels have somewhere to hang, and 区間 is the
    // invisible series the tooltip reads (#1285).
    expect(option.series?.map((series) => series.name)).toEqual([
      "場面",
      "区間",
      "ペース",
      "心拍",
      "最大心拍",
    ]);
    expect(seriesNamed(option, "場面")?.data).toEqual([[0, 0]]);
  });

  it("test_run_flow_only_uses_registered_series_types", () => {
    const option = renderFlow();

    // ECharts is tree-shaken: a series whose chart module is not registered in
    // lib/echarts.ts is accepted, drawn nowhere and reported nowhere. The max
    // heart-rate markers were exactly that until ScatterChart was registered
    // (#1283), while every assertion on the option object kept passing.
    const types = option.series?.map((series) => series.type) ?? [];
    expect(types.length).toBeGreaterThan(0);
    for (const type of types) {
      expect(REGISTERED_SERIES_TYPES).toContain(type);
    }

    const maxHr = seriesNamed(option, "最大心拍");
    expect(maxHr?.type).toBe("scatter");
    expect(maxHr?.data).toHaveLength(STEADY_SEGMENTS.length);
  });

  it("test_run_flow_component_has_no_fragment_rule", () => {
    const source = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "RunFlow.tsx"),
      "utf8",
    );

    // The report is the single fragment rule; a second copy here is how pace
    // and heart rate came to describe different runs.
    expect(source).not.toContain("MIN_SPLIT_KM");
    expect(source).not.toContain("kmLabels");
  });

  it("test_run_flow_uses_stacked_panels_and_the_ceiling", () => {
    const option = renderFlow();

    // Pace and heart rate share no unit, so they get a panel each on one
    // axis rather than two lines crossing on dual axes. The third grid is the
    // caption row above them.
    expect(option.grid).toHaveLength(3);

    const ceiling = seriesNamed(option, "心拍")?.markLine?.data?.find(
      (item) => item.yAxis === 150,
    );
    expect(ceiling?.lineStyle?.type).toBe("dotted");
    expect(ceiling?.lineStyle?.color).toBe(THRESHOLD_LINE.warn);
  });

  it("draws no ceiling on a day without a prescription", () => {
    const option = renderFlow(STEADY_FLOW, MOMENTS, TIMELINE, null);

    expect(
      seriesNamed(option, "心拍")?.markLine?.data?.some(
        (item) => item.yAxis != null,
      ),
    ).toBe(false);
  });
});

describe("RunFlow tooltip", () => {
  // A kilometre, a 0.1 km lap, another kilometre: the short lap is what a
  // nearest-midpoint lookup gets wrong.
  const UNEVEN_FLOW = flowOf([
    segment(1, [0, 1], [0, 400], { pace: 400, hr: 140, max: 146 }),
    segment(2, [1, 1.1], [400, 440], { pace: 395, hr: 141, max: 147 }),
    segment(3, [1.1, 2.1], [440, 840], { pace: 390, hr: 142, max: 148 }),
  ]);

  it("test_only_the_carrier_series_answers_the_tooltip", () => {
    const option = renderFlow();

    // ECharts reports the nearest *point*, and a step has two: left to the
    // drawn series the tooltip showed pace twice and lost 心拍 (#1285).
    for (const name of ["場面", "ペース", "心拍", "最大心拍"]) {
      expect(seriesNamed(option, name)?.tooltip?.show).toBe(false);
    }
    expect(seriesNamed(option, CARRIER_SERIES_NAME)?.tooltip?.show).not.toBe(
      false,
    );
  });

  it("test_carrier_points_sit_inside_their_segment", () => {
    const option = renderFlow();

    const points = seriesNamed(option, CARRIER_SERIES_NAME)?.data ?? [];
    expect(points).toHaveLength(STEADY_SEGMENTS.length * 2);
    STEADY_SEGMENTS.forEach((drawn, index) => {
      for (const [x] of [points[index * 2], points[index * 2 + 1]]) {
        expect(x).toBeGreaterThan(drawn.start_km);
        expect(x).toBeLessThan(drawn.end_km);
      }
    });
  });

  it("test_segment_at_picks_the_containing_segment_next_to_a_short_one", () => {
    const [first, second] = UNEVEN_FLOW.segments;

    expect(segmentAt(UNEVEN_FLOW, 0.95)).toBe(first);
    expect(segmentAt(UNEVEN_FLOW, 1.05)).toBe(second);
    expect(segmentAt(UNEVEN_FLOW, 1.0005)).toBe(second);
    expect(segmentAt(UNEVEN_FLOW, -1)).toBeNull();
    expect(segmentAt(UNEVEN_FLOW, Number.NaN)).toBeNull();
  });

  it("test_segment_tooltip_has_one_row_per_series", () => {
    const flow = flowOf([
      segment(1, [0, 1], [0, 400], { pace: 400, hr: 140, max: 146 }),
      segment(2, [1, 2], [400, 807], { pace: 407, hr: 145, max: 149 }),
    ]);

    const html = segmentTooltipHtml(flow, flow.segments[1]);

    expect(html).toContain("1.0–2.0 km");
    expect(html.match(/ペース/g)).toHaveLength(1);
    expect(html.match(/平均心拍/g)).toHaveLength(1);
    expect(html.match(/最大心拍/g)).toHaveLength(1);
    expect(html).toContain("6:47/km");
    expect(html).toContain("145 bpm");
    expect(html).toContain("149 bpm");
    // One step only: its name would say nothing the header does not.
    expect(html).not.toContain("本編");
  });

  it("test_segment_tooltip_names_the_step_on_a_time_axis", () => {
    const flow = flowOf(
      [
        segment(1, [0, 1.5], [0, 600], { pace: 400, hr: 130, max: 140 }, "wu"),
        segment(2, [1.5, 2.1], [600, 780], { pace: 300, hr: 170, max: 176 }, "r1"),
      ],
      {
        axis: "time",
        steps: [
          step("wu", ["ウォームアップ", "アップ"], [1, 1]),
          step("r1", ["1本目", "1"], [2, 2]),
        ],
      },
    );

    const html = segmentTooltipHtml(flow, flow.segments[1]);

    expect(html).toContain("1本目 · 10:00–13:00");
    expect(html).not.toContain(" km<");
  });

  it("test_segment_tooltip_prints_a_dash_for_a_missing_value", () => {
    const flow = flowOf([
      segment(1, [0, 1], [0, 400], { pace: 400, hr: 140, max: null }),
    ]);

    const html = segmentTooltipHtml(flow, flow.segments[0]);

    expect(html).toMatch(/最大心拍<\/span><span[^>]*>-<\/span>/);
    expect(html).not.toContain("null");
  });
});

describe("RunFlow scene bands", () => {
  it("test_single_split_scene_is_a_band", () => {
    const option = renderFlow(STEADY_FLOW, [
      moment("m1", "start", [1, 1], { km_from: 0, km_to: 1 }),
    ]);

    // A one-kilometre scene is a band, not the zero-width line the category
    // axis drew for it (#1269).
    expect(bandSpans(option)).toEqual([[0, 1]]);
  });

  it("keeps adjacent bands countable", () => {
    const option = renderFlow();

    const areas = seriesNamed(option, "ペース")?.markArea?.data ?? [];
    expect(areas.map((range) => range[0].itemStyle?.color)).toEqual([
      SCENE_TINTS[0],
      SCENE_TINTS[1],
      SCENE_TINTS[0],
      SCENE_TINTS[1],
    ]);
    expect(seriesNamed(option, "ペース")?.markLine?.data).toHaveLength(4);
  });

  it("test_walk_break_draws_one_band_per_walk_split", () => {
    const segments = Array.from({ length: 25 }, (_, index) =>
      segment(index + 1, [index, index + 1], [index * 420, (index + 1) * 420], {
        pace: 420,
        hr: 140,
      }),
    );
    const walk = moment("m1", "walk_break", [14, 22], {
      km_from: 13,
      km_to: 22,
      label_ja: "13・19・21 km 付近",
      facts: { split_list: [14, 20, 22], km_list: [13, 19, 21] },
    });
    const between = moment("m2", "surge", [17, 17], {
      km_from: 16,
      km_to: 17,
    });

    const option = renderFlow(flowOf(segments), [walk, between]);

    // One slab over km 13–22 both overstated the break and swallowed the
    // scene that happened at km 17, so the numbers read "④③" (#1269).
    expect(bandSpans(option)).toEqual([
      [13, 14],
      [19, 20],
      [21, 22],
      [16, 17],
    ]);
    expect(bandCaptions(option)).toEqual(["①", "①", "①", "②"]);
    const areas = seriesNamed(option, "ペース")?.markArea?.data ?? [];
    expect(areas.slice(0, 3).map((range) => range[0].itemStyle?.color)).toEqual([
      SCENE_TINTS[0],
      SCENE_TINTS[0],
      SCENE_TINTS[0],
    ]);
  });

  it("test_step_scene_caption_uses_short_label", () => {
    const rest = (totalS: number) => {
      const segments = [
        segment(1, [0, 3], [0, 960], { pace: 320, hr: 168 }, "s1"),
        segment(2, [3, 3.2], [960, 1080], { pace: 600, hr: 150 }, "s2"),
        segment(3, [3.2, 6], [1080, totalS], { pace: 330, hr: 170 }, "s3"),
      ];
      return flowOf(segments, {
        axis: "time",
        total_s: totalS,
        steps: [
          step("s1", ["1本目", "1本目"], [1, 1]),
          step("s2", ["レスト1", "R"], [2, 2]),
          step("s3", ["2本目", "2本目"], [3, 3]),
        ],
      });
    };
    const restScene = moment("m3", "rest", [2, 2], {
      unit: "step",
      label_ja: "レスト1",
      step_id: "s2",
      t_from_s: 960,
      t_to_s: 1080,
    });
    const before = [
      moment("m1", "rep", [1, 1], { unit: "step", step_id: "s1" }),
      moment("m2", "rep", [1, 1], { unit: "step", step_id: "s1" }),
    ];

    // Two of twenty minutes is wide enough for the step's short name.
    const wide = renderFlow(rest(1200), [...before, restScene]);
    expect(bandCaptions(wide)[2]).toBe("③ R");

    // The same rest inside a forty-minute session is a sliver: number only.
    const narrow = renderFlow(rest(2400), [...before, restScene]);
    expect(bandCaptions(narrow)[2]).toBe("③");
  });

  it("test_km_scene_covering_a_whole_step_is_captioned_with_the_step", () => {
    const segments = Array.from({ length: 10 }, (_, index) =>
      segment(
        index + 1,
        [index, index + 1],
        [index * 400, (index + 1) * 400],
        { pace: 400, hr: 145 },
        index === 0 ? "s1" : index < 6 ? "s2" : "s3",
      ),
    );
    const steps = [
      step("s1", ["ウォームアップ", "アップ"], [1, 1]),
      step("s2", ["本編", "本編"], [2, 6]),
      step("s3", ["クールダウン", "ダウン"], [7, 10]),
    ];
    const flow = flowOf(segments, { steps });
    const first = moment("m1", "start", [1, 1], { km_from: 0, km_to: 1 });

    // The tempo run's widest band read "②" while its neighbours read
    // "① アップ" and "③ ダウン": a km scene that is a whole step is named
    // after that step (#1269).
    const whole = renderFlow(flow, [
      first,
      moment("m2", "steady", [2, 6], { km_from: 1, km_to: 6 }),
    ]);
    expect(bandCaptions(whole)[1]).toBe("② 本編");

    // A stretch inside a step is still just a stretch of road.
    const part = renderFlow(flow, [
      first,
      moment("m3", "surge", [4, 5], { km_from: 3, km_to: 5 }),
    ]);
    expect(bandCaptions(part)[1]).toBe("②");
  });
});

describe("RunFlow scene list", () => {
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

  it("test_scene_list_uses_label_ja", () => {
    // The label is the report's, verbatim: a lap number is not a kilometre,
    // and a rep session is narrated by its steps (#1268).
    renderFlow(STEADY_FLOW, [
      moment("m1", "steady", [3, 5], { label_ja: "3–5 km" }),
      moment("m2", "work_set", [1, 5], { label_ja: "本編 0.9–5.9 km" }),
      moment("m3", "rep", [1, 1], { unit: "step", label_ja: "1本目" }),
    ], []);

    const rows = screen.getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("3–5 km");
    expect(rows[1]).toHaveTextContent("本編 0.9–5.9 km");
    expect(rows[2]).toHaveTextContent("1本目");
  });

  it("labels strides scene", () => {
    // A strides scene without a label of its own falls back to its kind's
    // Japanese name, never the bare "strides" key (#1298).
    renderFlow(
      STEADY_FLOW,
      [moment("m1", "strides", [3, 4], { unit: "step", label_ja: "" })],
      [],
    );

    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveTextContent("流し");
    expect(rows[0]).not.toHaveTextContent("strides");
  });

  it("keeps a scene the coach did not write about", () => {
    renderFlow(STEADY_FLOW, MOMENTS, [TIMELINE[0]]);

    // The run happened whether or not there was anything to say about it: the
    // scene keeps its band and its label, with nothing beside it.
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(4);
    expect(rows[1]).toHaveTextContent("2 km");
    expect(rows[1]).not.toHaveTextContent("登り");
  });

  it("test_scene_without_timeline_text_has_empty_text", () => {
    // Five scenes, four sentences: the coach may write fewer timeline items
    // than the report found scenes.
    const cooldown = moment("m5", "cooldown", [5, 5], {
      label_ja: "クールダウン",
    });
    renderFlow(STEADY_FLOW, [...MOMENTS, cooldown], TIMELINE);

    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(5);
    const last = rows[4];
    // The label once, in its own column; the text cell empty — repeating the
    // label as the sentence read as a note that said nothing (#1277).
    expect(last.textContent?.match(/クールダウン/g)).toHaveLength(1);
    const cells = Array.from(last.querySelectorAll("span"));
    expect(cells[cells.length - 1].textContent).toBe("");
  });
});
