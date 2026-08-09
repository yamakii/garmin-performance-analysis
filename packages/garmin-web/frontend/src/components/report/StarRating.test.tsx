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
   * `text-gold` on `bg-gold/10` measures 1.99:1 (Issue #911) — the score is
   * real text, so it has to carry an AA-safe amber instead. The star glyphs
   * stay gold: they are aria-hidden decoration duplicated by this very pill.
   */
  it("test_star_score_not_gold_text", () => {
    const { unmount } = render(<StarRating text="★★★★☆ 4.2/5.0" />);

    const score = screen.getByText("4.2 / 5.0");
    expect(score).not.toHaveClass("text-gold");
    expect(score).toHaveClass("text-amber-800");
    unmount();

    render(<StarBadge score={3.5} />);

    const badge = screen.getByText("★ 3.5");
    expect(badge).not.toHaveClass("text-gold");
    expect(badge).toHaveClass("text-amber-800");
  });

  it("test_star_rating_unparseable_falls_back_to_plain_text", () => {
    render(<StarRating text="評価なし" />);

    const fallback = screen.getByText("評価なし");
    expect(fallback).not.toHaveClass("text-gold");
    expect(fallback).toHaveClass("text-amber-800");
  });
});
