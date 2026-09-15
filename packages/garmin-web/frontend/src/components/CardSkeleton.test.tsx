import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CardSkeleton from "./CardSkeleton";

describe("CardSkeleton", () => {
  it("renders a status region with aria-busy", () => {
    render(<CardSkeleton label="走行量" />);

    const status = screen.getByRole("status");
    expect(status).toBeInTheDocument();
    expect(status).toHaveAttribute("aria-busy", "true");
    // The label names which block is pending for assistive tech.
    expect(status).toHaveAttribute("aria-label", "走行量");
  });

  it("test_card_skeleton_dash_placeholder", () => {
    render(<CardSkeleton />);

    const status = screen.getByRole("status");
    // Same shell as the resolved block so swapping in content causes no shift.
    expect(status).toHaveClass("border-t", "border-hairline");
    // A mono dash stands in for the number; nothing pulses (#1116).
    expect(status).toHaveTextContent("——");
    expect(status.querySelector(".animate-pulse")).toBeNull();
  });
});
