import type { SectionResult } from "../../types";
import { splitLead } from "../../utils/leadSentence";
import { extractStarSuffix } from "../../utils/starSuffix";
import Disclosure from "../Disclosure";
import FallbackFields from "./FallbackFields";
import MarkdownText from "./MarkdownText";
import ReportCard, {
  isRecord,
  META_LABEL,
  SUBCARD,
  SUBHEADING,
} from "./ReportCard";
import StarBadge from "./StarBadge";

const FIELDS: { key: string; label: string }[] = [
  { key: "efficiency", label: "フォーム効率" },
  { key: "evaluation", label: "心拍効率評価" },
  { key: "form_trend", label: "フォームトレンド" },
];

const KNOWN_KEYS = ["metadata", ...FIELDS.map((field) => field.key)];

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

/** "期待 <value><unit>" note from an expected metric, or null. */
function expectedNote(
  expected: number | null,
  unit: string,
  digits: number,
): string | null {
  if (expected == null) {
    return null;
  }
  return `期待${expected.toFixed(digits)}${unit}`;
}

/** "偏差 ±<value><unit>" note from a delta, or null. */
function deltaNote(
  delta: number | null,
  unit: string,
  digits: number,
): string | null {
  if (delta == null) {
    return null;
  }
  const sign = delta > 0 ? "+" : "";
  return `偏差${sign}${delta.toFixed(digits)}${unit}`;
}

function joinNotes(...parts: (string | null)[]): string | null {
  const kept = parts.filter((part): part is string => part != null);
  return kept.length > 0 ? kept.join(" / ") : null;
}

type Tile = {
  label: string;
  value: number | null;
  unit: string;
  digits: number;
  rating: string | null;
  note: string | null;
};

function sectionField(
  section: SectionResult | undefined,
  key: "efficiency" | "evaluation",
): string {
  const data = isRecord(section?.data) ? section.data : null;
  return typeof data?.[key] === "string" ? (data[key] as string) : "";
}

/** The prose field whose trailing star rating is the section's verdict. */
function sectionRating(section: SectionResult | undefined) {
  return extractStarSuffix(sectionField(section, "efficiency")).rating;
}

/** First sentence of the HR-efficiency evaluation: the card's lead line. */
function evaluationLead(section: SectionResult | undefined): string | null {
  const { body } = extractStarSuffix(sectionField(section, "evaluation"));
  const { lead } = splitLead(body);
  return lead !== "" ? lead : null;
}

/**
 * Efficiency analysis: structured form metrics as stat tiles alongside the
 * analyst's prose evaluation.
 *
 * Tiles read the authoritative, pace-based, expectation-relative evaluation
 * (form_evaluations table) so the values and stars match the prose. The
 * CV-based form_efficiency table is no longer used here (#292).
 *
 * The tiles are the headline (#905): the star rating is lifted out of the
 * efficiency prose into a heading badge, the HR evaluation's opening sentence
 * becomes a one-line verdict, and the three prose fields fold into a
 * disclosure so the numbers are never buried under paragraphs.
 */
export default function EfficiencyReport({
  section,
  formEvaluations,
}: {
  section: SectionResult | undefined;
  formEvaluations?: Record<string, unknown> | null;
}) {
  const fe = formEvaluations;
  const rating = sectionRating(section);
  const lead = evaluationLead(section);

  // form_evaluations may be null for unevaluated activities; show prose only.
  const tiles: Tile[] = fe
    ? [
        {
          label: "接地時間",
          value: asNumber(fe.gct_ms_actual),
          unit: "ms",
          digits: 0,
          rating: asString(fe.gct_star_rating),
          note: joinNotes(
            expectedNote(asNumber(fe.gct_ms_expected), "ms", 0),
            deltaNote(asNumber(fe.gct_delta_pct), "%", 1),
          ),
        },
        {
          label: "上下動",
          value: asNumber(fe.vo_cm_actual),
          unit: "cm",
          digits: 1,
          rating: asString(fe.vo_star_rating),
          // VO stores an absolute cm delta (vo_delta_cm), not a percentage.
          note: joinNotes(
            expectedNote(asNumber(fe.vo_cm_expected), "cm", 1),
            deltaNote(asNumber(fe.vo_delta_cm), "cm", 1),
          ),
        },
        {
          label: "上下動比",
          value: asNumber(fe.vr_pct_actual),
          unit: "%",
          digits: 1,
          rating: asString(fe.vr_star_rating),
          note: joinNotes(
            expectedNote(asNumber(fe.vr_pct_expected), "%", 1),
            deltaNote(asNumber(fe.vr_delta_pct), "%", 1),
          ),
        },
      ]
    : [];

  const stats = tiles.filter((tile) => tile.value != null);

  // Power efficiency is a self-baseline-relative descriptor, not a star tile in
  // the GCT/VO/VR row (#836). It gets its own subsection: the descriptor label
  // (power_efficiency_rating) as the headline, with power and actual-vs-expected
  // speed as supporting evidence. Shown only when the activity has power data.
  const powerAvg = asNumber(fe?.power_avg_w);
  const powerWkg = asNumber(fe?.power_wkg);
  const powerLabel = asString(fe?.power_efficiency_rating);
  const speedActual = asNumber(fe?.speed_actual_mps);
  const speedExpected = asNumber(fe?.speed_expected_mps);
  const hasPower = powerAvg != null;

  return (
    <ReportCard
      title="効率分析"
      section={section}
      badge={rating && <StarBadge score={rating.score} />}
    >
      {(data) => (
        <>
          {stats.length > 0 && (
            // GCT / VO / VR are three fixed form-metric tiles (#836).
            <dl className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
              {stats.map(({ label, value, unit, digits, rating, note }) => (
                <div key={label} className={SUBCARD}>
                  <dt className={META_LABEL}>{label}</dt>
                  {/* GCT / VO / VR share the violet form-metric color (#214). */}
                  <dd className="mt-0.5 font-numeric text-2xl leading-none font-semibold tabular-nums text-metric-form">
                    {value!.toFixed(digits)}
                    <span className="ml-0.5 text-xs font-normal text-slate-500">
                      {unit}
                    </span>
                  </dd>
                  {rating && (
                    <dd className="text-xs text-slate-500">{rating}</dd>
                  )}
                  {note && (
                    <dd className="text-[11px] leading-tight text-slate-500">
                      {note}
                    </dd>
                  )}
                </div>
              ))}
            </dl>
          )}
          {hasPower && (
            <div className="mb-4">
              <h3 className={`mb-1 ${SUBHEADING}`}>
                パワー効率（自己ベースライン比）
              </h3>
              <dl className={SUBCARD}>
                {powerLabel && (
                  <dd className="text-base font-semibold text-metric-form">
                    {powerLabel}
                  </dd>
                )}
                <dd className="mt-0.5 text-xs text-slate-500">
                  {powerAvg.toFixed(0)} W
                  {powerWkg != null && ` / ${powerWkg.toFixed(2)} W/kg`}
                </dd>
                {speedActual != null && speedExpected != null && (
                  <dd className="text-[11px] leading-tight text-slate-500">
                    実測 {speedActual.toFixed(2)} m/s / 期待{" "}
                    {speedExpected.toFixed(2)} m/s
                  </dd>
                )}
              </dl>
            </div>
          )}
          {lead != null && (
            <p className="mb-3 text-sm leading-relaxed font-medium text-ink">
              {lead}
            </p>
          )}
          <Disclosure title="分析の詳細">
            {FIELDS.map(({ key, label }) => {
              const text = data[key];
              if (typeof text !== "string") {
                return null;
              }
              // The efficiency verdict already shows as a heading badge, so
              // its star suffix is stripped from the paragraph.
              const prose =
                key === "efficiency" ? extractStarSuffix(text).body : text;
              return (
                <div key={key} className="mt-3 first:mt-1">
                  <h3 className={`mb-1 ${SUBHEADING}`}>{label}</h3>
                  <MarkdownText text={prose} />
                </div>
              );
            })}
          </Disclosure>
          <FallbackFields data={data} exclude={KNOWN_KEYS} />
        </>
      )}
    </ReportCard>
  );
}
