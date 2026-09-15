import { describe, expect, it } from "vitest";
import { flaggedSplitIndices } from "./splitAnomalies";

function section(data: Record<string, unknown>) {
  return { data, parse_error: false, raw: null };
}

describe("flaggedSplitIndices", () => {
  it("test_flagged_split_indices", () => {
    const flagged = flaggedSplitIndices(
      section({
        analyses: {
          split_3: "接地時間が異常に長い区間でした。",
          split_4: "ペース・心拍とも安定しています。",
        },
      }),
    );

    expect(flagged).toEqual(new Set([3]));
  });

  it("flags 注意 as well as 異常", () => {
    const flagged = flaggedSplitIndices(
      section({
        analyses: {
          split_1: "心拍の跳ね上がりに注意が必要です。",
          split_2: "狙いどおりの巡航でした。",
          split_7: "上下動比が異常値です。",
        },
      }),
    );

    expect(flagged).toEqual(new Set([1, 7]));
  });

  it("returns an empty set for missing or unusable sections", () => {
    // No section at all, no analyses object, a parse error, and keys that are
    // not `split_N` all mean "nothing to highlight".
    expect(flaggedSplitIndices(undefined)).toEqual(new Set());
    expect(flaggedSplitIndices(section({ highlights: "異常なし" }))).toEqual(
      new Set(),
    );
    expect(
      flaggedSplitIndices({ data: null, parse_error: true, raw: "{" }),
    ).toEqual(new Set());
    expect(
      flaggedSplitIndices(
        section({ analyses: { overall: "異常あり", split_x: "異常あり" } }),
      ),
    ).toEqual(new Set());
  });

  it("ignores non-string analysis values", () => {
    expect(
      flaggedSplitIndices(section({ analyses: { split_2: { note: "異常" } } })),
    ).toEqual(new Set());
  });
});
