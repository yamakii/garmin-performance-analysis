import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StarBadge from "./StarBadge";
import StarRating, { parseStarRating } from "./StarRating";

describe("StarRating", () => {
  it("test_parse_star_rating", () => {
    expect(parseStarRating("★★★★☆ 4.2/5.0")).toEqual({ score: 4.2, max: 5 });
    expect(parseStarRating("評価なし")).toBeNull();
  });

  /**
   * The `star` token is a 3:1 non-text color, so only the aria-hidden glyphs
   * may wear it; the score is real text and stays in ink (#911, #1116).
   */
  it("test_star_score_not_star_colored", () => {
    const { unmount } = render(<StarRating text="★★★★☆ 4.2/5.0" />);

    const score = screen.getByText("4.2 / 5.0");
    expect(score).not.toHaveClass("text-star");
    expect(score).toHaveClass("text-ink-soft");
    expect(screen.getByLabelText("評価 4.2 / 5.0")).toHaveClass("font-mono");
    unmount();

    render(<StarBadge score={3.5} />);

    const badge = screen.getByLabelText("評価 3.5 / 5.0");
    expect(badge).toHaveTextContent("★ 3.5");
    expect(badge).toHaveClass("text-ink-soft");
    expect(badge.querySelector(".text-star")).not.toBeNull();
  });

  it("test_star_rating_unparseable_falls_back_to_plain_text", () => {
    render(<StarRating text="評価なし" />);

    const fallback = screen.getByText("評価なし");
    expect(fallback).not.toHaveClass("text-star");
    expect(fallback).toHaveClass("text-ink-soft");
  });
});
