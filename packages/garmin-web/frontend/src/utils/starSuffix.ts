/**
 * Split the trailing star rating off an analysis sentence.
 *
 * The section agents end evaluative prose with a `(★★★★☆ 4.2/5.0)` suffix
 * (`.claude/rules/analysis/analysis-standards.md`). For a visual-first layout
 * the rating belongs in a dedicated badge rather than buried at the end of a
 * paragraph, so this helper peels it off and hands back both halves.
 *
 * Only a suffix at the very end of the text is recognised — a mid-sentence
 * `(★★★☆☆ 3.0/5.0)` is left untouched so the prose is never silently cut.
 */
export interface StarSuffix {
  stars: string;
  score: number;
}

/**
 * `(★★★★☆ 4.2/5.0)` at end of string. Half-width and full-width parentheses
 * both occur in the Japanese prose; the `/5.0` denominator is written as
 * `5.0` today but `5` is tolerated.
 */
const STAR_SUFFIX_RE =
  /[(（]\s*([★☆]+)\s*(\d+(?:\.\d+)?)\s*\/\s*5(?:\.0)?\s*[)）]\s*$/;

export function extractStarSuffix(text: string): {
  body: string;
  rating: StarSuffix | null;
} {
  const match = STAR_SUFFIX_RE.exec(text);
  if (match == null) {
    return { body: text, rating: null };
  }
  const score = Number(match[2]);
  if (!Number.isFinite(score)) {
    return { body: text, rating: null };
  }
  return {
    body: text.slice(0, match.index).trimEnd(),
    rating: { stars: match[1], score },
  };
}
