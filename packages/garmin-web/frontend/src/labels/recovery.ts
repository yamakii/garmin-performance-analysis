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

/**
 * The same recommendation read as a state of recovery, which is the question
 * `/condition` answers (#1120). Home says what to do today ("イージー推奨");
 * the condition page says why ("回復に注意") — one value, two sentences, both
 * written here so neither page invents a third wording.
 */
export const RECOVERY_STATE_LABELS: Record<RecoveryRecommendation, string> = {
  quality: "回復は良好",
  moderate: "回復はほぼ正常",
  easy: "回復に注意",
  rest: "回復不足",
  unknown: "回復データなし",
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
