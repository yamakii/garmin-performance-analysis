import { describe, expect, it } from "vitest";
import { PICTOGRAPH_RE } from "./emoji";
import { ratingMeta } from "./verdictRating";

describe("ratingMeta", () => {
  it("maps each verdict mark to its word", () => {
    expect(ratingMeta("✅")).toEqual({ tone: "good", label: "良好" });
    expect(ratingMeta("🟡→消化済")).toEqual({ tone: "warn", label: "注意" });
    expect(ratingMeta("🔴→対応済")).toEqual({ tone: "bad", label: "要改善" });
  });

  it("test_unknown_rating_label_has_no_emoji", () => {
    // Pre-split reviews stored marks outside the three (⚪); the label keeps
    // the words and drops the emoji, and a bare mark reads 判定なし (#1428).
    expect(ratingMeta("⚪")).toEqual({ tone: "info", label: "判定なし" });
    expect(ratingMeta("⚪ 保留")).toEqual({ tone: "info", label: "保留" });
    expect(ratingMeta("保留")).toEqual({ tone: "info", label: "保留" });
    for (const rating of ["⚪", "⚪ 保留", "🟢", "⭐"]) {
      expect(ratingMeta(rating).label).not.toMatch(PICTOGRAPH_RE);
    }
  });
});
