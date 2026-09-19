import * as echarts from "echarts/core";
import { BarChart, LineChart, ScatterChart } from "echarts/charts";
import {
  DataZoomComponent,
  GraphicComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

/** The chart module behind each `series[].type` this app draws. */
const CHART_MODULES = {
  line: LineChart,
  bar: BarChart,
  scatter: ScatterChart,
} as const;

/**
 * The `series[].type` values the registered chart modules can draw. An option
 * builder that uses any other type draws nothing and reports nothing, so tests
 * of the builders check their series against this list (#1283). Derived from
 * the same table as the registration, so the two cannot drift.
 */
export const REGISTERED_SERIES_TYPES = Object.keys(
  CHART_MODULES,
) as (keyof typeof CHART_MODULES)[];

/**
 * Chart types / components actually used in this app: line + bar + scatter
 * charts; grid/tooltip/legend/markLine/markArea/dataZoom/graphic components;
 * canvas renderer.
 *
 * Exported so a unit test can assert the list stays in sync with the features
 * the option builders rely on. An omission fails *silently* at runtime — the
 * form quality bands (`markArea`) were configured but never painted until
 * MarkAreaComponent was registered here (Issue #913), and the run-flow chart's
 * max-heart-rate markers (`type: "scatter"`) were in the option, in the legend
 * and in the unit tests, and on no canvas, until ScatterChart was (#1283).
 */
export const REGISTERED_ECHARTS_MODULES = [
  ...Object.values(CHART_MODULES),
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  MarkAreaComponent,
  DataZoomComponent,
  GraphicComponent,
  CanvasRenderer,
];

echarts.use(REGISTERED_ECHARTS_MODULES);

export { echarts };
export type { EChartsOption } from "echarts";
