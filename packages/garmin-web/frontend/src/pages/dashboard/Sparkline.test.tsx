import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Sparkline from "./Sparkline";

// Collect the option instead of rendering to canvas (jsdom has none).
const captured = vi.hoisted(() => ({ options: [] as SparkOption[] }));

vi.mock("../../components/EChart", () => ({
  default: (props: { option: unknown }) => {
    captured.options.push(props.option as SparkOption);
    return null;
  },
}));

type SparkOption = { yAxis?: { scale?: boolean } };

function optionOf(element: Parameters<typeof render>[0]): SparkOption {
  captured.options.length = 0;
  render(element);
  return captured.options[0];
}

describe("Sparkline", () => {
  it("test_sparkline_bar_zero_baseline", () => {
    // Bars encode magnitude by length: cropping the zero baseline would make
    // 26.4 -> 6.5 km look like a total collapse.
    const bars = optionOf(
      <Sparkline
        type="bar"
        data={[26.4, 6.5]}
        labels={["2026-06-22", "2026-06-29"]}
        color="#16213a"
        ariaLabel="週間走行距離ミニグラフ"
      />,
    );
    expect(bars.yAxis?.scale).toBeFalsy();

    // Lines encode shape only, so they keep the zoomed (scale) axis.
    const line = optionOf(
      <Sparkline
        data={[45, 48]}
        labels={["2026-06-30", "2026-07-01"]}
        color="#e11d48"
        ariaLabel="安静時心拍ミニグラフ"
      />,
    );
    expect(line.yAxis?.scale).toBe(true);
  });
});
