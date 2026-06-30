import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CardSkeleton from "./CardSkeleton";

describe("CardSkeleton", () => {
  it("renders a status region with aria-busy", () => {
    render(<CardSkeleton label="走行量" />);

    const status = screen.getByRole("status");
    expect(status).toBeInTheDocument();
    expect(status).toHaveAttribute("aria-busy", "true");
    // The label names which card is pending for assistive tech.
    expect(status).toHaveAttribute("aria-label", "走行量");
  });

  it("applies card shell classes", () => {
    render(<CardSkeleton />);

    const status = screen.getByRole("status");
    // Same shell as the resolved cards so swapping in content causes no shift.
    for (const cls of [
      "rounded-xl",
      "border",
      "border-slate-200",
      "bg-white",
      "p-5",
      "shadow-sm",
    ]) {
      expect(status.className).toContain(cls);
    }
  });
});
