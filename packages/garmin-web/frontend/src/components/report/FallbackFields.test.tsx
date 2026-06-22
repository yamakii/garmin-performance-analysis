import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderValue } from "./FallbackFields";

/** Render a ReactNode and return its visible text. */
function text(node: ReturnType<typeof renderValue>): string {
  const { container } = render(<>{node}</>);
  return container.textContent ?? "";
}

describe("renderValue", () => {
  it("test_renderValue_formats_float_number", () => {
    // Un-consumed numeric fields must not leak floating-point noise (#493).
    expect(text(renderValue(4.2000000000001))).toBe("4.2");
  });

  it("test_renderValue_keeps_integer", () => {
    expect(text(renderValue(5))).toBe("5");
  });

  it("test_renderValue_string_unchanged", () => {
    // Strings still render as Markdown text (regression guard).
    expect(text(renderValue("テンポ走としての完成度は高い"))).toBe(
      "テンポ走としての完成度は高い",
    );
  });
});
