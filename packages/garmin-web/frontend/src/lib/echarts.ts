import * as echarts from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import {
  DataZoomComponent,
  GraphicComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

// Register only the chart types / components actually used in this app.
// Audited usage: line + bar charts; grid/tooltip/legend/markLine/dataZoom/graphic
// components; canvas renderer. Keep this list in sync if new chart features are added.
echarts.use([
  LineChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  DataZoomComponent,
  GraphicComponent,
  CanvasRenderer,
]);

export { echarts };
export type { EChartsOption } from "echarts";
