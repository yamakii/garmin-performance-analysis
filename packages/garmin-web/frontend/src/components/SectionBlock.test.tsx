import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SectionBlock from "./SectionBlock";

describe("SectionBlock", () => {
  it("test_section_block_renders_h2_and_note", () => {
    render(
      <SectionBlock id="recovery" title="回復トレンド" note="4週" noteMono>
        <p>本文</p>
      </SectionBlock>,
    );

    expect(
      screen.getByRole("heading", { level: 2, name: "回復トレンド" }),
    ).toBeInTheDocument();
    expect(screen.getByText("4週")).toHaveClass("font-mono");
    expect(screen.getByText("本文")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2 }).closest("section"),
    ).toHaveAttribute("id", "recovery");
  });

  it("renders a prose note in sans and drops it when absent", () => {
    const { container, rerender } = render(
      <SectionBlock title="効率" note="GCT と上下動比">
        <p>本文</p>
      </SectionBlock>,
    );
    expect(screen.getByText("GCT と上下動比").className).not.toMatch(
      /font-mono/,
    );

    rerender(
      <SectionBlock title="効率" headingExtra={<span> ★★★★☆</span>}>
        <p>本文</p>
      </SectionBlock>,
    );
    expect(container.querySelectorAll("p")).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(
      "効率 ★★★★☆",
    );
  });
});
