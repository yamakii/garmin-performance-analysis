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
