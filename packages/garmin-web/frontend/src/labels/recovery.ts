import type {
  HrvStatus,
  RecoveryRecommendation,
  RhrTrend,
} from "../types";

/**
 * Japanese wording for the recovery enums, shared by every surface that shows
 * them (Issue #915).
 *
 * The same `recommendation` used to read "質練OK / 中程度 / イージー / 休養"
 * on the condition page and "質練OK / 通常ラン OK / イージー推奨 / 休養推奨"
 * in the home hero, and the same `hrv.status` was "バランス / 低下" on one
 * page and "標準 / 低め" on another. One value must have one name, so the
 * words live here and the components only choose colors.
 */

/** Morning go/no-go recommendation. */
export const RECOMMENDATION_LABELS: Record<RecoveryRecommendation, string> = {
  quality: "質練OK",
  moderate: "通常ラン OK",
  easy: "イージー推奨",
  rest: "休養推奨",
  unknown: "データなし",
};

/** Overnight HRV status against the personal baseline. */
export const HRV_STATUS_LABELS: Record<Exclude<HrvStatus, null>, string> = {
  balanced: "標準",
  low: "低め",
  high: "高め",
};

/** Direction of the 7-day resting-HR median. */
export const RHR_TREND_LABELS: Record<Exclude<RhrTrend, null>, string> = {
  improving: "改善",
  stable: "安定",
  fatigued: "疲労",
};
