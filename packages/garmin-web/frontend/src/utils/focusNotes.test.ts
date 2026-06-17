import { describe, expect, it } from "vitest";
import { parseFocusNotes } from "./focusNotes";

describe("parseFocusNotes", () => {
  it("test_parseFocusNotes_splits_by_brackets", () => {
    expect(parseFocusNotes("前文【A】aaa【B】bbb")).toEqual([
      { title: null, body: "前文" },
      { title: "A", body: "aaa" },
      { title: "B", body: "bbb" },
    ]);
  });

  it("test_parseFocusNotes_splits_by_brackets_without_preamble", () => {
    expect(parseFocusNotes("【ボトルネック】後半失速【ロング走】距離を踏む")).toEqual([
      { title: "ボトルネック", body: "後半失速" },
      { title: "ロング走", body: "距離を踏む" },
    ]);
  });

  it("test_parseFocusNotes_no_brackets", () => {
    const text = "見出しの無いただの長文メモ。これを1ブロックで返す。";
    expect(parseFocusNotes(text)).toEqual([{ title: null, body: text }]);
  });

  it("test_parseFocusNotes_empty", () => {
    expect(parseFocusNotes(null)).toEqual([]);
    expect(parseFocusNotes("")).toEqual([]);
    expect(parseFocusNotes("   ")).toEqual([]);
  });
});
