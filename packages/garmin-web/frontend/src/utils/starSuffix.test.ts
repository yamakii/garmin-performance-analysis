import { describe, expect, it } from "vitest";
import { extractStarSuffix } from "./starSuffix";

describe("extractStarSuffix", () => {
  it("test_extract_star_suffix_present", () => {
    const result = extractStarSuffix("良好でした。(★★★★☆ 4.2/5.0)");

    expect(result.body).toBe("良好でした。");
    expect(result.rating).toEqual({ stars: "★★★★☆", score: 4.2 });
  });

  it("test_extract_star_suffix_absent", () => {
    const result = extractStarSuffix("評価文のみ");

    expect(result.body).toBe("評価文のみ");
    expect(result.rating).toBeNull();
  });

  it("test_extract_star_suffix_fullwidth_parentheses", () => {
    const result = extractStarSuffix("心拍管理は安定しています。（★★★☆☆ 3.0/5.0）");

    expect(result.body).toBe("心拍管理は安定しています。");
    expect(result.rating).toEqual({ stars: "★★★☆☆", score: 3.0 });
  });

  it("test_extract_star_suffix_ignores_midsentence_rating", () => {
    const text = "(★★★★☆ 4.2/5.0) を維持したいところです。";
    const result = extractStarSuffix(text);

    expect(result.body).toBe(text);
    expect(result.rating).toBeNull();
  });
});
