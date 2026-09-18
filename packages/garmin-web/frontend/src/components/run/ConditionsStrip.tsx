import type { JSX } from "react";
import type { RunConditions } from "../../types";
import { formatNumber } from "../../utils/formatNumber";

/** Japanese name per terrain band, as the analysis contract classifies it. */
const TERRAIN_LABELS: Record<string, string> = {
  flat: "平坦",
  undulating: "起伏あり",
  hilly: "丘陵",
  mountainous: "山岳",
};

/**
 * 気温 / 湿度 / 風 / 地形 / 獲得標高 as one mono line.
 *
 * The temperature is the weather station's, never the device's: a watch sits
 * against a warm arm and reads 5-8 °C high, which would turn every summer run
 * into a heat story it was not. Fields the run has no reading for are simply
 * left out rather than printed as dashes.
 */
export function conditionsParts(conditions: RunConditions): string[] {
  const parts: string[] = [];
  if (conditions.temp_c != null) {
    parts.push(`気温 ${formatNumber(conditions.temp_c, 1)}°C`);
  }
  if (conditions.humidity_pct != null) {
    parts.push(`湿度 ${formatNumber(conditions.humidity_pct, 0)}%`);
  }
  if (conditions.wind_mps != null) {
    parts.push(`風 ${formatNumber(conditions.wind_mps, 1)}m/s`);
  }
  if (conditions.terrain != null) {
    parts.push(
      `地形 ${TERRAIN_LABELS[conditions.terrain] ?? conditions.terrain}`,
    );
  }
  if (conditions.elevation_gain_m != null) {
    parts.push(`獲得標高 ${formatNumber(conditions.elevation_gain_m, 0)}m`);
  }
  return parts;
}

/** The conditions the run was actually run in, one mono line (#1252). */
export default function ConditionsStrip({
  conditions,
}: {
  conditions: RunConditions | null;
}): JSX.Element | null {
  if (conditions == null) {
    return null;
  }
  const parts = conditionsParts(conditions);
  if (parts.length === 0) {
    return null;
  }
  return (
    <p className="font-mono text-[13px] text-ink-muted">{parts.join(" · ")}</p>
  );
}
