export interface ParsedStarRating {
  score: number;
  max: number;
}

/** Parses a "★★★★☆ 4.2/5.0" style rating string into numbers. */
export function parseStarRating(text: string): ParsedStarRating | null {
  const match = /(\d+(?:\.\d+)?)\s*\/\s*(\d+(?:\.\d+)?)/.exec(text);
  if (!match) {
    return null;
  }
  const score = Number(match[1]);
  const max = Number(match[2]);
  if (!Number.isFinite(score) || !Number.isFinite(max) || max <= 0) {
    return null;
  }
  return { score, max };
}

const STAR_COUNT = 5;

/**
 * Visual star rating parsed from the summary section's star_rating string.
 * Unparseable strings are rendered as-is (graceful degradation).
 *
 * The glyph row is decorative (aria-hidden, duplicated by the numeric score
 * and the aria-label) and takes the `star` token, which is a 3:1 non-text
 * color; the score is real text and so stays in ink (#911, #1116).
 */
export default function StarRating({
  text,
  size = "md",
}: {
  text: string;
  size?: "md" | "lg";
}) {
  const parsed = parseStarRating(text);
  if (!parsed) {
    return <span className="font-mono text-sm text-ink-soft">{text}</span>;
  }
  const filled = Math.min(
    STAR_COUNT,
    Math.max(0, Math.round((parsed.score / parsed.max) * STAR_COUNT)),
  );
  const starClass = size === "lg" ? "text-[28px]" : "text-base";
  return (
    <span
      className="inline-flex items-baseline gap-2 font-mono"
      aria-label={`評価 ${parsed.score.toFixed(1)} / ${parsed.max.toFixed(1)}`}
    >
      <span
        aria-hidden="true"
        className={`${starClass} leading-none font-medium tracking-[0.05em]`}
      >
        <span className="text-star">{"★".repeat(filled)}</span>
        <span className="text-metric-compare">{"★".repeat(STAR_COUNT - filled)}</span>
      </span>
      <span className="text-xs font-medium text-ink-soft">
        {parsed.score.toFixed(1)} / {parsed.max.toFixed(1)}
      </span>
    </span>
  );
}
