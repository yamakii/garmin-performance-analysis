import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import VerdictLine from "./VerdictLine";

describe("VerdictLine", () => {
  it("test_verdict_line_heading_and_tone", () => {
    const { rerender } = render(
      <VerdictLine
        verdict="休養推奨。"
        verdictTone="bad"
        rest="今日の処方はありません。"
      />,
    );

    // The verdict is the page heading, not a stray paragraph (#912).
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading).toHaveTextContent("休養推奨。今日の処方はありません。");
    expect(screen.getByText("休養推奨。")).toHaveClass("text-status-bad");
    // The second half stays regular weight and one step softer.
    expect(screen.getByText("今日の処方はありません。")).toHaveClass(
      "font-normal",
      "text-ink-soft",
    );

    rerender(<VerdictLine verdict="質練OK。" rest="今日はテンポ 6km。" />);
    expect(screen.getByText("質練OK。").className).not.toMatch(/text-status-/);
  });

  it("test_verdict_line_sub_size_is_not_a_heading", () => {
    render(
      <VerdictLine size="sub" verdict="処方どおり" rest=" · 特記なし" />,
    );

    // A page that already has a title keeps it as the `h1`; the verdict about
    // it is a paragraph one step down the scale (#1270).
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    const line = screen.getByText("処方どおり").parentElement as HTMLElement;
    expect(line.tagName).toBe("P");
    expect(line.className).toContain("text-xl");
    expect(line.className).not.toContain("text-[36px]");
    expect(line.className).not.toContain("text-[40px]");
  });

  it("renders the lead and actions only when given", () => {
    const { container, rerender } = render(<VerdictLine verdict="質練OK。" />);
    expect(container.querySelectorAll("p")).toHaveLength(0);

    rerender(
      <VerdictLine
        verdict="質練OK。"
        lead="HRVは基準内です"
        actions={<button type="button">今日のメニュー詳細</button>}
      />,
    );
    expect(screen.getByText("HRVは基準内です")).toHaveClass("text-ink-soft");
    expect(
      screen.getByRole("button", { name: "今日のメニュー詳細" }),
    ).toBeInTheDocument();
  });
});
