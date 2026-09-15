import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SectionHeading from "./SectionHeading";

describe("SectionHeading", () => {
  it("test_section_heading_no_eyebrow", () => {
    const { container } = render(
      <SectionHeading title="今週" note="09/14 – 09/20" />,
    );

    expect(
      screen.getByRole("heading", { level: 1, name: "今週" }),
    ).toBeInTheDocument();
    // The note is a mono caption beside the heading...
    expect(screen.getByText("09/14 – 09/20")).toHaveClass("font-mono");
    // ...and nothing restates the heading in tracked-out English (#1116).
    expect(container.querySelector(".uppercase")).toBeNull();
  });

  it("renders title as h1 by default and h2 when as=h2", () => {
    const { rerender } = render(<SectionHeading title="トレンド" />);
    expect(
      screen.getByRole("heading", { level: 1, name: "トレンド" }),
    ).toBeInTheDocument();

    rerender(<SectionHeading title="トレンド" as="h2" />);
    expect(
      screen.getByRole("heading", { level: 2, name: "トレンド" }),
    ).toBeInTheDocument();
  });

  it("omits the note element when none is given", () => {
    const { container } = render(<SectionHeading title="目標" />);

    expect(container.querySelectorAll("p")).toHaveLength(0);
  });
});
