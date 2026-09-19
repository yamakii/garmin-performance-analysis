import { SVGRenderer } from "echarts/renderers";
import { afterEach, describe, expect, it } from "vitest";
import { echarts } from "../../lib/echarts";
import type { RunFlowData, RunFlowSegment } from "../../types";
import { runFlowOption, segmentAt } from "./RunFlow";

// The option-object tests cannot see what ECharts does with the option: which
// series answer a hover, and at which value. That is exactly where the tooltip
// went wrong (#1285), so these run the real axis trigger, headless, on SVG.
echarts.use([SVGRenderer]);
// jsdom has no canvas to measure text with; a fixed advance is enough here,
// and without it every label logs a "getContext not implemented" error.
echarts.setPlatformAPI({
  measureText: (text: string) => ({ width: text.length * 7 }) as TextMetrics,
});

const WIDTH = 720;
const HEIGHT = 320;
const GRID_LEFT = 56;
const GRID_RIGHT = 16;
const PACE_PANEL_Y = 76;
const HR_PANEL_Y = 200;

function segment(
  index: number,
  startKm: number,
  endKm: number,
): RunFlowSegment {
  return {
    split_from: index + 1,
    split_to: index + 1,
    step_id: "s1",
    start_km: startKm,
    end_km: endKm,
    start_s: startKm * 400,
    end_s: endKm * 400,
    pace_s_per_km: 400 - index * 5,
    avg_hr: 140 + index,
    max_hr: 146 + index,
  };
}

// A 1 km lap, a 0.1 km fragment-sized lap, then three more kilometres: the
// short one is what a midpoint-based lookup gets wrong.
const BOUNDS = [0, 1, 1.1, 2.1, 3.1, 4.1];
const SEGMENTS = BOUNDS.slice(0, -1).map((from, index) =>
  segment(index, from, BOUNDS[index + 1]),
);
const FLOW: RunFlowData = {
  axis: "distance",
  total_km: 4.1,
  total_s: 1640,
  segments: SEGMENTS,
  steps: [],
  fragments: { count: 0, distance_km: 0 },
};

function pixelOf(km: number): number {
  return GRID_LEFT + (km / FLOW.total_km) * (WIDTH - GRID_LEFT - GRID_RIGHT);
}

type Param = { seriesName?: string; axisValue?: number };

function hover(km: number, y: number): { params: Param[]; html: string } {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const chart = echarts.init(host, undefined, {
    renderer: "svg",
    width: WIDTH,
    height: HEIGHT,
  });
  const option = runFlowOption(FLOW, [], 150) as {
    tooltip: { formatter: (params: unknown) => string };
  };
  const inner = option.tooltip.formatter;
  const seen: { params: Param[]; html: string } = { params: [], html: "" };
  option.tooltip.formatter = (params: unknown) => {
    seen.params = (Array.isArray(params) ? params : [params]) as Param[];
    seen.html = inner(params);
    return seen.html;
  };
  chart.setOption(option as never);
  chart.dispatchAction({ type: "showTip", x: pixelOf(km), y });
  chart.dispose();
  host.remove();
  return seen;
}

describe("RunFlow tooltip at runtime", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("test_hover_yields_one_carrier_item_inside_the_hovered_segment", () => {
    // 0.95 km: inside the first kilometre, but nearer to the midpoint of the
    // 0.1 km lap beside it than to its own.
    for (const [km, expected] of [
      [0.95, 0],
      [1.05, 1],
      [1.6, 2],
      [4.0, 4],
    ] as const) {
      for (const y of [PACE_PANEL_Y, HR_PANEL_Y]) {
        const { params, html } = hover(km, y);

        expect(params.map((param) => param.seriesName)).toEqual(
          params.map(() => "区間"),
        );
        expect(params.length).toBeGreaterThan(0);
        expect(segmentAt(FLOW, Number(params[0].axisValue))).toBe(
          SEGMENTS[expected],
        );
        expect(html.match(/ペース/g)).toHaveLength(1);
        expect(html.match(/平均心拍/g)).toHaveLength(1);
        expect(html.match(/最大心拍/g)).toHaveLength(1);
        expect(html).toContain(`${140 + expected} bpm`);
        expect(html).toContain(`${146 + expected} bpm`);
      }
    }
  });
});
