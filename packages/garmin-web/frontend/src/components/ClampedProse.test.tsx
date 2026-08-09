import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "../test/utils";
import ClampedProse from "./ClampedProse";

const SHORT_TEXT = "今週は順調でした。\n心拍も安定しています。";

/** 10 lines — well past both the line and the character budget of lines=3. */
const LONG_TEXT = Array.from(
  { length: 10 },
  (_, i) => `${i + 1}行目の解説テキストです。`,
).join("\n");

describe("ClampedProse", () => {
  it("test_clamped_prose_short_text_no_toggle", () => {
    render(<ClampedProse text={SHORT_TEXT} lines={3} />);

    // Both lines are rendered in one paragraph (newlines survive as
    // `whitespace-pre-line`; the query normalizer collapses them).
    expect(screen.getByText(/心拍も安定しています。/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("test_clamped_prose_long_text_shows_toggle", () => {
    render(<ClampedProse text={LONG_TEXT} lines={3} />);

    const toggle = screen.getByRole("button", { name: "続きを読む" });
    fireEvent.click(toggle);

    expect(screen.getByRole("button", { name: "閉じる" })).toBeInTheDocument();
    expect(screen.queryByText("続きを読む")).not.toBeInTheDocument();
    // The full text stays in the DOM either way — expanding only drops the
    // clamp — so the last line proves the whole narration is available.
    expect(screen.getByText(/10行目の解説テキストです。/)).toBeInTheDocument();
  });

  it("test_clamped_prose_toggle_target_size", () => {
    render(<ClampedProse text={LONG_TEXT} lines={3} />);

    // xs text alone is a ~16px tap target; the vertical padding lifts it past
    // the 24px minimum without moving the label (#912).
    const toggle = screen.getByRole("button", { name: "続きを読む" });
    expect(toggle.className).toMatch(/(^|\s)py-1\.5(\s|$)/);
    expect(toggle).toHaveClass("px-2");
    expect(toggle).toHaveClass("-mx-2");
  });

  it("test_clamped_prose_markdown_mode", () => {
    const { container } = render(
      <ClampedProse text="ペースは**安定**しています。" markdown />,
    );

    const strong = container.querySelector("strong");
    expect(strong).not.toBeNull();
    expect(strong?.textContent).toBe("安定");
  });
});
