import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StatusBadge from "./StatusBadge";

describe("StatusBadge", () => {
  it("test_status_badge_tones", () => {
    render(
      <>
        <StatusBadge tone="good">良好</StatusBadge>
        <StatusBadge tone="warn">注意</StatusBadge>
        <StatusBadge tone="bad">未実施</StatusBadge>
        <StatusBadge tone="today">今日</StatusBadge>
      </>,
    );

    // 良 carries no fill: color is reserved for the exceptions (#1116).
    const good = screen.getByText("良好");
    expect(good).toHaveClass("border-hairline", "text-ink-soft");
    expect(good.className).not.toMatch(/(^|\s)bg-/);
    expect(good).toHaveAttribute("data-tone", "good");

    const warn = screen.getByText("注意");
    expect(warn).toHaveClass("bg-warn-tint", "text-status-warn");

    const bad = screen.getByText("未実施");
    expect(bad).toHaveClass("bg-bad-tint", "text-status-bad");

    expect(screen.getByText("今日")).toHaveClass("bg-accent", "text-paper");
  });

  it("renders as a mono tag, not a pill", () => {
    render(<StatusBadge tone="info">順調</StatusBadge>);

    const badge = screen.getByText("順調");
    expect(badge).toHaveClass("font-mono", "rounded-sm");
    expect(badge.className).not.toContain(["rounded", "full"].join("-"));
  });
});
