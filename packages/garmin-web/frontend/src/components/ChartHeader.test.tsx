import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ChartHeader from "./ChartHeader";

describe("ChartHeader", () => {
  it("renders the title, note and a toned status", () => {
    const { container, rerender } = render(
      <ChartHeader title="ACWR" note="直近8週" status="注意" statusTone="warn" />,
    );

    expect(container.firstElementChild).toHaveClass("font-mono", "text-xs");
    expect(screen.getByText("ACWR")).toHaveClass("font-semibold", "text-ink");
    expect(screen.getByText("直近8週")).toBeInTheDocument();
    const status = screen.getByText("注意");
    expect(status).toHaveClass("ml-auto", "text-status-warn");

    rerender(<ChartHeader title="ACWR" status="最適" />);
    expect(screen.getByText("最適").className).not.toMatch(/text-status-/);
  });

  it("omits the note and the status when absent", () => {
    const { container } = render(<ChartHeader title="HRV" />);

    expect(container.querySelectorAll("span")).toHaveLength(1);
  });
});
