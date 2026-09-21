const MAX_SCORE = 5;

/**
 * Compact `★ 4.0` marker for a rating lifted out of prose (`extractStarSuffix`).
 *
 * A one-glance marker for a section heading or a phase row, where the score
 * has to sit next to a label without dominating it. Mono, star-colored glyph,
 * ink score: no pill, no tint (#1116).
 */
export default function StarBadge({ score }: { score: number }) {
  return (
    <span
      aria-label={`評価 ${score.toFixed(1)} / ${MAX_SCORE.toFixed(1)}`}
      className="inline-flex shrink-0 items-baseline gap-1 font-mono text-xs font-medium text-ink-soft"
    >
      <span aria-hidden="true" className="text-star">
        ★
      </span>{" "}
      {score.toFixed(1)}
    </span>
  );
}
