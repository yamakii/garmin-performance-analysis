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
    return <span className="text-sm text-amber-800">{text}</span>;
  }
  const filled = Math.min(
    STAR_COUNT,
    Math.max(0, Math.round((parsed.score / parsed.max) * STAR_COUNT)),
  );
  const starClass = size === "lg" ? "text-2xl" : "text-base";
  return (
    <span
      className="inline-flex items-center gap-2"
      aria-label={`評価 ${parsed.score.toFixed(1)} / ${parsed.max.toFixed(1)}`}
    >
      {/*
       * The glyph row is decorative (aria-hidden, duplicated by the numeric
       * pill and the aria-label), so it keeps the vivid gold/slate pair. The
       * pill carries the actual score as text and so must clear AA — gold is
       * 1.99:1 on its own tint, amber-800 is 6.75:1 (Issue #911).
       */}
      <span aria-hidden="true" className={`${starClass} leading-none`}>
        <span className="text-gold">{"★".repeat(filled)}</span>
        <span className="text-slate-300">{"★".repeat(STAR_COUNT - filled)}</span>
      </span>
      <span className="rounded-full bg-gold/10 px-2 py-0.5 text-xs font-semibold tabular-nums text-amber-800">
        {parsed.score.toFixed(1)} / {parsed.max.toFixed(1)}
      </span>
    </span>
  );
}
