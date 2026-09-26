import type { StatusTone } from "../components/StatusBadge";
import { PICTOGRAPH_RE } from "./emoji";

const PICTOGRAPHS = new RegExp(PICTOGRAPH_RE.source, "gu");

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
 * and keeps whatever words the agent wrote as its own label -- without its
 * emoji (#1428): pre-split reviews stored marks such as ⚪, and the site shows
 * none. A rating that is nothing but an unknown mark reads 判定なし.
 */
export function ratingMeta(rating: string): RatingMeta {
  const known = RATING_MARKS.find(({ mark }) => rating.includes(mark));
  if (known != null) {
    return { tone: known.tone, label: known.label };
  }
  const words = rating.replace(PICTOGRAPHS, "").trim();
  return { tone: "info", label: words === "" ? "判定なし" : words };
}

/** The marks in verdict order (good → warn → bad), with their words. */
export function ratingMarks(): { mark: string; label: string }[] {
  return RATING_MARKS.map(({ mark, label }) => ({ mark, label }));
}
