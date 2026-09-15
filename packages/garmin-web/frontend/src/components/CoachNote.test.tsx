import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import CoachNote from "./CoachNote";

describe("CoachNote", () => {
  it("test_coach_note_source_link", () => {
    render(
      <MemoryRouter>
        <CoachNote
          source={{
            label: "週次レビュー 09/07 →",
            to: "/weekly-reviews/2026-09-07",
          }}
        >
          ロング走は時間×HRで管理
        </CoachNote>
      </MemoryRouter>,
    );

    const link = screen.getByRole("link", { name: "週次レビュー 09/07 →" });
    expect(link).toHaveAttribute("href", "/weekly-reviews/2026-09-07");
    expect(link).toHaveClass("font-mono", "whitespace-nowrap");

    // The note is a rule and body text, not a tinted callout.
    const note = screen.getByText(/ロング走は時間×HRで管理/);
    expect(note).toHaveClass("border-l-2", "border-ink", "text-ink-soft");
  });

  it("test_coach_note_renders_bold_markdown", () => {
    render(
      <MemoryRouter>
        <CoachNote>装備は **股を覆う長丈のインナー** で走る</CoachNote>
      </MemoryRouter>,
    );

    // The coach writes markdown; the asterisks are emphasis, not characters.
    const strong = screen.getByText("股を覆う長丈のインナー");
    expect(strong.tagName).toBe("STRONG");
    expect(document.body.textContent).not.toContain("**");
  });

  it("test_coach_note_keeps_react_node_children", () => {
    render(
      <MemoryRouter>
        <CoachNote>
          <span data-testid="composed">x</span>
        </CoachNote>
      </MemoryRouter>,
    );

    // Callers that compose their own nodes are passed through untouched.
    expect(screen.getByTestId("composed")).toHaveTextContent("x");
  });

  it("emphasises the line when strong is set", () => {
    render(
      <MemoryRouter>
        <CoachNote strong>次回は心拍 145 以下で 10km</CoachNote>
      </MemoryRouter>,
    );

    const note = screen.getByText("次回は心拍 145 以下で 10km");
    expect(note).toHaveClass("font-bold", "text-ink");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
