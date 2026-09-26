/**
 * Words for the energy-balance read (Issue #1439, reader #1434).
 *
 * The reader decides every status, verdict and exclusion; this module only
 * names them, so the panel and the weekly review say the same thing. Pure
 * functions, kept apart from the panel so the wording is tested on its own.
 */
import { formatSigned } from "../../utils/formatNumber";
import type { EnergyBalance } from "../../types";

export type EnergyTone = "muted" | "warn";

/** Why a window day is left out of the mean (`window.excluded[].reason`). */
const REASON_LABELS: Record<string, string> = {
  in_progress: "集計中",
  pending: "同期待ち",
  not_logged: "記録なし",
  suspect_low: "少なめ・未確認",
  athlete_reported_incomplete: "記録漏れ",
  low_wear: "装着不足",
  unsynced: "未同期",
  no_data: "データなし",
};

/**
 * Where the window mean sits against the block's target band. Named by side
 * rather than depth: under 維持 a mean above the band is a surplus, which
 * "shallower" would misname.
 */
const VERDICT_TEXT: Record<string, string> = {
  deeper_than_target: "目標帯より赤字側",
  within_target: "目標帯内",
  shallower_than_target: "目標帯より黒字側",
};

/** Off-target on either side is the exception the design system colours. */
const OFF_TARGET = new Set(["deeper_than_target", "shallower_than_target"]);

/** Calibration verdicts worth a line; `insufficient` stays silent. */
const CALIBRATION_TEXT: Record<string, string> = {
  consistent: "体重の推移と整合",
  logged_deficit_exceeds_weight: "体重の減りより赤字が大きい（記録漏れの可能性）",
  logged_deficit_below_weight: "体重の減りより赤字が小さい",
};

/** Label for an exclusion reason; an unknown code is shown as-is. */
export function reasonLabel(reason: string): string {
  return REASON_LABELS[reason] ?? reason;
}

/** Text for a verdict; null when there is none, an unknown string as-is. */
export function verdictText(verdict: string | null | undefined): string | null {
  if (verdict == null || verdict === "") {
    return null;
  }
  return VERDICT_TEXT[verdict] ?? verdict;
}

/** warn only when the mean left the target band. */
export function verdictTone(verdict: string | null | undefined): EnergyTone {
  return verdict != null && OFF_TARGET.has(verdict) ? "warn" : "muted";
}

/** The calibration line, or null while there is nothing to say. */
export function calibrationText(status: string | null | undefined): string | null {
  return status != null ? (CALIBRATION_TEXT[status] ?? null) : null;
}

/** "MM/DD" from an ISO date. */
export function monthDay(iso: string): string {
  const match = /^\d{4}-(\d{2})-(\d{2})/.exec(iso);
  return match != null ? `${match[1]}/${match[2]}` : iso;
}

/** "目標帯 -150〜+150（維持）", or "目標帯なし" when the block sets none. */
export function bandNote(data: EnergyBalance): string {
  const { band_kcal: band, weight_mode: mode, crosses_block_boundary } =
    data.target;
  const base =
    band != null
      ? `目標帯 ${formatSigned(band[0], 0)}〜${formatSigned(band[1], 0)}${
          mode != null ? `（${mode}）` : ""
        }`
      : "目標帯なし";
  return crosses_block_boundary ? `${base} · ブロック境目を含む` : base;
}

/**
 * The status at the right end of the chart header. First match wins: a lapse
 * outranks everything (the numbers are stale), then a thin window (no verdict
 * is drawn from it), then the verdict itself.
 */
export function headerStatus(data: EnergyBalance): {
  text: string;
  tone: EnergyTone;
} {
  const { window, logging, target } = data;
  if (logging.lapsed) {
    return { text: `${logging.days_since_last_log ?? 0}日記録なし`, tone: "warn" };
  }
  if (window.status !== "ok") {
    return {
      text: `判定なし · ${window.paired_days}/${window.required_days}日`,
      tone: "muted",
    };
  }
  const text = verdictText(target.verdict);
  if (text == null) {
    return { text: "判定なし", tone: "muted" };
  }
  return {
    text: `平均 ${formatSigned(window.mean_balance_kcal, 0)} · ${text}`,
    tone: verdictTone(target.verdict),
  };
}
