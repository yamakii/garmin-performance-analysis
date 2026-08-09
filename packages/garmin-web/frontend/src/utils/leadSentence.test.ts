import { describe, expect, it } from "vitest";
import { splitLead } from "./leadSentence";

describe("splitLead", () => {
  it("test_split_lead_takes_first_sentence", () => {
    const { lead, body } = splitLead(
      "有酸素ベースの安定したランでした。心拍は平均144bpmで推移しました。後半も崩れていません。",
    );

    expect(lead).toBe("有酸素ベースの安定したランでした。");
    expect(body).toBe("心拍は平均144bpmで推移しました。後半も崩れていません。");
  });

  it("test_split_lead_without_period_keeps_whole_text", () => {
    const { lead, body } = splitLead("  句点のない一文  ");

    expect(lead).toBe("句点のない一文");
    expect(body).toBe("");
  });

  it("test_split_lead_single_sentence_has_empty_body", () => {
    const { lead, body } = splitLead("一文だけの要約です。");

    expect(lead).toBe("一文だけの要約です。");
    expect(body).toBe("");
  });
});
