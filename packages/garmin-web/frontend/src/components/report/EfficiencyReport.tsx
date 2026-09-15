import type { SectionResult } from "../../types";
import { splitLead } from "../../utils/leadSentence";
import { extractStarSuffix } from "../../utils/starSuffix";
import Disclosure from "../Disclosure";
import VitalsRow, { type VitalItem } from "../VitalsRow";
import FallbackFields from "./FallbackFields";
import MarkdownText from "./MarkdownText";
import ReportCard, { isRecord, SUBHEADING } from "./ReportCard";
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
  expected: number | null;
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
 * GCT, VO and VR are all "lower is better": a value above its pace-based
 * expectation is the adverse direction, and only that direction earns the warn
 * colour. Everything else — better than expected, or no expectation to compare
 * against — stays muted, because in this system colour marks exceptions only.
 */
function noteTone(
  value: number | null,
  expected: number | null,
): "muted" | "warn" {
  return value != null && expected != null && value > expected
    ? "warn"
    : "muted";
}

/**
 * Efficiency analysis: the three form metrics as one vitals row, then the
 * analyst's reading of them.
 *
 * The numbers come from the authoritative, pace-based, expectation-relative
 * evaluation (form_evaluations table) so they and the prose agree; the
 * CV-based form_efficiency table is no longer used here (#292). The row leads
 * (#905): the star rating is lifted out of the efficiency prose into the
 * heading, the HR evaluation's opening sentence becomes a one-line verdict,
 * and the three prose fields fold into a disclosure so the figures are never
 * buried under paragraphs.
 */
export default function EfficiencyReport({
  section,
  formEvaluations,
  id,
}: {
  section: SectionResult | undefined;
  formEvaluations?: Record<string, unknown> | null;
  id?: string;
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
          expected: asNumber(fe.gct_ms_expected),
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
          expected: asNumber(fe.vo_cm_expected),
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
          expected: asNumber(fe.vr_pct_expected),
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

  const vitals: VitalItem[] = tiles
    .filter((tile) => tile.value != null)
    .map((tile) => ({
      label: tile.label,
      value: tile.value!.toFixed(tile.digits),
      unit: tile.unit,
      // The per-metric stars keep their own colour inside the note so a warn
      // expectation does not recolour the rating it sits next to.
      note: (
        <>
          {tile.rating != null && (
            <span className="mr-1.5 text-star">{tile.rating}</span>
          )}
          {tile.note}
        </>
      ),
      noteTone: noteTone(tile.value, tile.expected),
    }));

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
      id={id}
      title="効率分析"
      section={section}
      badge={rating && <StarBadge score={rating.score} />}
    >
      {(data) => (
        <div className="flex flex-col gap-4">
          {vitals.length > 0 && (
            // GCT / VO / VR are the three fixed form metrics (#836).
            <VitalsRow ariaLabel="フォーム指標" items={vitals} columns={3} />
          )}
          {hasPower && (
            <div className="border-t border-hairline pt-3">
              <h3 className={`mb-1 ${SUBHEADING}`}>
                パワー効率（自己ベースライン比）
              </h3>
              <dl>
                {powerLabel && (
                  <dd className="text-[15px] font-bold text-ink">
                    {powerLabel}
                  </dd>
                )}
                <dd className="mt-0.5 font-mono text-xs text-ink-muted">
                  {powerAvg.toFixed(0)} W
                  {powerWkg != null && ` / ${powerWkg.toFixed(2)} W/kg`}
                </dd>
                {speedActual != null && speedExpected != null && (
                  <dd className="font-mono text-xs leading-tight text-ink-muted">
                    実測 {speedActual.toFixed(2)} m/s / 期待{" "}
                    {speedExpected.toFixed(2)} m/s
                  </dd>
                )}
              </dl>
            </div>
          )}
          {lead != null && (
            <p className="text-[15px] leading-[1.7] text-ink-soft">{lead}</p>
          )}
          <Disclosure title="分析の詳細">
            {FIELDS.map(({ key, label }) => {
              const text = data[key];
              if (typeof text !== "string") {
                return null;
              }
              // The efficiency verdict already shows in the heading, so its
              // star suffix is stripped from the paragraph.
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
        </div>
      )}
    </ReportCard>
  );
}
