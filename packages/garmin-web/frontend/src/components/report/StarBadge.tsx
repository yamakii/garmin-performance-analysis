const MAX_SCORE = 5;

/**
 * Compact `★ 4.0` pill for a rating lifted out of prose (`extractStarSuffix`).
 *
 * Unlike `StarRating` — the hero five-star display of the summary section —
 * this is a one-glance marker for a section heading or a timeline node, where
 * the score has to sit next to a label without dominating it.
 */
export default function StarBadge({ score }: { score: number }) {
  return (
    <span
      aria-label={`評価 ${score.toFixed(1)} / ${MAX_SCORE.toFixed(1)}`}
      className="inline-flex shrink-0 items-center rounded-full bg-gold/10 px-2 py-0.5 text-xs font-semibold tabular-nums text-gold"
    >
      {`★ ${score.toFixed(1)}`}
    </span>
  );
}
