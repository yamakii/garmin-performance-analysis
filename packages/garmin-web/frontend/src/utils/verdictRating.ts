import type { StatusTone } from "../components/StatusBadge";

/**
 * Verdict marks the weekly-review agent emits, with the status tone and the
 * Japanese word each one stands for.
 *
 * The word is not decoration (#912): color alone must never carry meaning, and
 * a screen reader announces 🔴 as "large red circle", which says nothing about
 * the session. Every surface that shows a verdict emoji — the review table, the
 * Home plan rows, the review list counts — reads its wording from here so they
 * cannot drift apart.
 */
const RATING_MARKS: { mark: string; tone: StatusTone; label: string }[] = [
  { mark: "✅", tone: "good", label: "良好" },
  { mark: "🟡", tone: "warn", label: "注意" },
  { mark: "🔴", tone: "bad", label: "要改善" },
];

export interface RatingMeta {
  tone: StatusTone;
  label: string;
}

/**
 * Tone + word for a verdict rating. The mark is matched by containment so a
 * decorated rating ("✅ 完了") still resolves; an unknown rating stays neutral
 * and keeps whatever text the agent wrote as its own label.
 */
export function ratingMeta(rating: string): RatingMeta {
  const known = RATING_MARKS.find(({ mark }) => rating.includes(mark));
  return known != null
    ? { tone: known.tone, label: known.label }
    : { tone: "info", label: rating };
}

/** The marks in verdict order (good → warn → bad), with their words. */
export function ratingMarks(): { mark: string; label: string }[] {
  return RATING_MARKS.map(({ mark, label }) => ({ mark, label }));
}
