import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StatusBadge from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders good tone with status-good token classes", () => {
    render(<StatusBadge tone="good">良好</StatusBadge>);

    const badge = screen.getByText("良好");
    expect(badge).toHaveClass("bg-status-good/10");
    expect(badge).toHaveClass("text-status-good");
  });

  it("renders warn tone with status-warn token classes", () => {
    render(<StatusBadge tone="warn">注意</StatusBadge>);

    const badge = screen.getByText("注意");
    expect(badge).toHaveClass("bg-status-warn/10");
    expect(badge).toHaveClass("text-status-warn");
  });

  it("renders children text", () => {
    render(<StatusBadge tone="info">順調</StatusBadge>);

    expect(screen.getByText("順調")).toBeInTheDocument();
  });
});
