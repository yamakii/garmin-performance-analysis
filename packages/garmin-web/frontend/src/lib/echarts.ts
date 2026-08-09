import * as echarts from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
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

/**
 * Chart types / components actually used in this app: line + bar charts;
 * grid/tooltip/legend/markLine/markArea/dataZoom/graphic components; canvas
 * renderer.
 *
 * Exported so a unit test can assert the list stays in sync with the features
 * the option builders rely on. An omission fails *silently* at runtime — the
 * form quality bands (`markArea`) were configured but never painted until
 * MarkAreaComponent was registered here (Issue #913).
 */
export const REGISTERED_ECHARTS_MODULES = [
  LineChart,
  BarChart,
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
