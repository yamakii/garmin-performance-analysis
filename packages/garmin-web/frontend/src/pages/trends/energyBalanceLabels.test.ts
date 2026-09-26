import { describe, expect, it } from "vitest";
import {
  bandNote,
  calibrationText,
  headerStatus,
  reasonLabel,
  verdictText,
  verdictTone,
} from "./energyBalanceLabels";
import { energyBalanceFixture } from "../../test/energyBalanceFixture";

describe("reasonLabel", () => {
  it("reasonLabel maps every exclusion reason", () => {
    expect(reasonLabel("not_logged")).toBe("記録なし");
    expect(reasonLabel("pending")).toBe("同期待ち");
    expect(reasonLabel("suspect_low")).toBe("少なめ・未確認");
    expect(reasonLabel("low_wear")).toBe("装着不足");
    expect(reasonLabel("in_progress")).toBe("集計中");
    expect(reasonLabel("unsynced")).toBe("未同期");
    expect(reasonLabel("no_data")).toBe("データなし");
    expect(reasonLabel("athlete_reported_incomplete")).toBe("記録漏れ");
  });

  it("shows an unknown reason code as-is", () => {
    expect(reasonLabel("something_new")).toBe("something_new");
  });
});

describe("verdictText and verdictTone", () => {
  it("verdictText and verdictTone", () => {
    expect(verdictText("deeper_than_target")).toBe("目標帯より赤字側");
    expect(verdictTone("deeper_than_target")).toBe("warn");
    expect(verdictText("within_target")).toBe("目標帯内");
    expect(verdictTone("within_target")).toBe("muted");
    expect(verdictText("shallower_than_target")).toBe("目標帯より黒字側");
    expect(verdictTone("shallower_than_target")).toBe("warn");
    expect(verdictText(null)).toBeNull();
    expect(verdictTone(null)).toBe("muted");
  });
});

describe("headerStatus", () => {
  it("headerStatus precedence", () => {
    const ok = energyBalanceFixture();
    expect(headerStatus(ok)).toEqual({
      text: "平均 -469 · 目標帯より赤字側",
      tone: "warn",
    });

    const insufficient = energyBalanceFixture({
      window: { status: "insufficient", paired_days: 4, required_days: 5 },
    });
    expect(headerStatus(insufficient)).toEqual({
      text: "判定なし · 4/5日",
      tone: "muted",
    });

    // A lapse outranks the verdict: the numbers behind it are stale.
    const lapsed = energyBalanceFixture({
      logging: { lapsed: true, days_since_last_log: 3 },
    });
    expect(headerStatus(lapsed)).toEqual({ text: "3日記録なし", tone: "warn" });
  });

  it("says 判定なし when the block sets no weight mode", () => {
    const data = energyBalanceFixture({
      target: { verdict: null, reason: "unknown_weight_mode", band_kcal: null },
    });
    expect(headerStatus(data)).toEqual({ text: "判定なし", tone: "muted" });
    expect(bandNote(data)).toBe("目標帯なし");
  });
});

describe("bandNote", () => {
  it("states the band with its mode, and a crossed block boundary", () => {
    expect(bandNote(energyBalanceFixture())).toBe("目標帯 -150〜+150（維持）");
    expect(
      bandNote(energyBalanceFixture({ target: { crosses_block_boundary: true } })),
    ).toBe("目標帯 -150〜+150（維持） · ブロック境目を含む");
  });
});

describe("calibrationText", () => {
  it("stays silent while the calibration is insufficient", () => {
    expect(calibrationText("insufficient")).toBeNull();
    expect(calibrationText("logged_deficit_exceeds_weight")).toBe(
      "体重の減りより赤字が大きい（記録漏れの可能性）",
    );
    expect(calibrationText("consistent")).toBe("体重の推移と整合");
  });
});
