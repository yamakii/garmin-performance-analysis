import { BarChart, LineChart, ScatterChart } from "echarts/charts";
import { ComponentModel } from "echarts/core";
import { describe, expect, it } from "vitest";
import { REGISTERED_ECHARTS_MODULES, REGISTERED_SERIES_TYPES } from "./echarts";

// ECharts is tree-shaken here, and an unregistered chart type fails silently:
// the option is accepted, nothing is drawn, nothing is logged. Tests that only
// inspect the option object cannot see it, so the registration has its own.
describe("echarts registration", () => {
  it("test_scatter_chart_is_registered", () => {
    // The run-flow chart draws max heart rate as hollow scatter markers (#1283).
    expect(REGISTERED_ECHARTS_MODULES).toContain(ScatterChart);
    expect(REGISTERED_SERIES_TYPES).toContain("scatter");
  });

  it("test_registered_series_types_match_the_chart_modules", () => {
    expect([...REGISTERED_SERIES_TYPES].sort()).toEqual([
      "bar",
      "line",
      "scatter",
    ]);
    for (const module of [LineChart, BarChart, ScatterChart]) {
      expect(REGISTERED_ECHARTS_MODULES).toContain(module);
    }
  });

  it("test_every_registered_series_type_has_a_series_model", () => {
    // The runtime's own answer, not our list's: after `echarts.use(...)` the
    // series model for each declared type exists in the ECharts registry.
    // (`hasClass` only looks at the main type, so it says yes to anything.)
    const registry = ComponentModel as unknown as {
      getClass(mainType: string, subType: string): unknown;
    };
    for (const type of REGISTERED_SERIES_TYPES) {
      expect(registry.getClass("series", type)).toBeDefined();
    }
    expect(registry.getClass("series", "pie")).toBeUndefined();
  });
});
