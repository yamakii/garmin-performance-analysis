import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SectionHeading from "./SectionHeading";

describe("SectionHeading", () => {
  it("renders eyebrow and title text", () => {
    render(<SectionHeading eyebrow="Trends" title="トレンド" />);

    expect(screen.getByText("Trends")).toBeInTheDocument();
    expect(screen.getByText("トレンド")).toBeInTheDocument();
  });

  it("renders title as h1 by default and h2 when as=h2", () => {
    const { rerender } = render(
      <SectionHeading eyebrow="Trends" title="トレンド" />,
    );
    expect(
      screen.getByRole("heading", { level: 1, name: "トレンド" }),
    ).toBeInTheDocument();

    rerender(<SectionHeading eyebrow="Trends" title="トレンド" as="h2" />);
    expect(
      screen.getByRole("heading", { level: 2, name: "トレンド" }),
    ).toBeInTheDocument();
  });

  it("eyebrow uses uppercase tracking style", () => {
    render(<SectionHeading eyebrow="Trends" title="トレンド" />);

    const eyebrow = screen.getByText("Trends");
    expect(eyebrow).toHaveClass("uppercase");
    expect(eyebrow).toHaveClass("tracking-[0.2em]");
  });
});
