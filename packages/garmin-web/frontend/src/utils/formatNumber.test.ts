import { describe, expect, it } from "vitest";
import {
  axisTooltipFormatter,
  formatNumber,
  formatSigned,
} from "./formatNumber";

describe("formatNumber", () => {
  it("test_formatNumber_strips_floating_point_noise", () => {
    expect(formatNumber(4.2000000000001, 1)).toBe("4.2");
  });

  it("test_formatNumber_strips_trailing_zeros", () => {
    expect(formatNumber(12.0, 1)).toBe("12");
    expect(formatNumber(1.5, 2)).toBe("1.5");
  });

  it("test_formatNumber_rounds_to_max_decimals", () => {
    expect(formatNumber(1.057, 2)).toBe("1.06");
  });

  it("test_formatNumber_integer_precision", () => {
    expect(formatNumber(152.4, 0)).toBe("152");
  });

  it("test_formatNumber_null_and_nan_return_dash", () => {
    expect(formatNumber(null)).toBe("-");
    expect(formatNumber(NaN)).toBe("-");
  });
});

describe("formatSigned", () => {
  it("test_format_signed", () => {
    expect(formatSigned(-0.0015, 4)).toBe("-0.0015");
    expect(formatSigned(0.0012, 4)).toBe("+0.0012");
    expect(formatSigned(0, 4)).toBe("±0.0000");
  });

  it("test_format_signed_keeps_trailing_decimals", () => {
    expect(formatSigned(1.5, 2)).toBe("+1.50");
    expect(formatSigned(-2, 1)).toBe("-2.0");
  });

  it("test_format_signed_rounded_away_value_is_neutral", () => {
    // -0.00004 rounds to 0.0000, so a "-" in front of zeros would mislead.
    expect(formatSigned(-0.00004, 4)).toBe("±0.0000");
    expect(formatSigned(-0, 1)).toBe("±0.0");
  });

  it("test_format_signed_null_and_nan_return_dash", () => {
    expect(formatSigned(null, 4)).toBe("-");
    expect(formatSigned(undefined, 4)).toBe("-");
    expect(formatSigned(NaN, 4)).toBe("-");
  });
});

describe("axisTooltipFormatter", () => {
  it("test_axisTooltipFormatter_per_series_precision", () => {
    const formatter = axisTooltipFormatter({ "週間距離 (km)": 1, ACWR: 2 });
    const out = formatter([
      {
        seriesName: "週間距離 (km)",
        marker: "●",
        value: 12.34,
        axisValueLabel: "2025-W20",
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      } as any,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      { seriesName: "ACWR", marker: "○", value: 1.057 } as any,
    ]);
    expect(out).toContain("12.3");
    expect(out).toContain("1.06");
    expect(out).toContain("●");
    expect(out).toContain("2025-W20");
  });

  it("test_axisTooltipFormatter_fallback_precision", () => {
    const formatter = axisTooltipFormatter({}, 1);
    const out = formatter([
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      { seriesName: "未指定", marker: "●", value: 3.456 } as any,
    ]);
    expect(out).toContain("3.5");
  });

  it("test_axisTooltipFormatter_handles_null_values", () => {
    const formatter = axisTooltipFormatter({ 系列: 1 });
    const out = formatter([
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      { seriesName: "系列", marker: "●", value: null } as any,
    ]);
    expect(out).toContain("-");
  });
});
