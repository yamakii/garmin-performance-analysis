import type { SectionResult } from "../types";

/**
 * Words the split analyst uses when a kilometre deviates from the rest of the
 * run ("接地時間が異常に長い", "心拍の跳ね上がりに注意"). The agent writes
 * Japanese prose, not a flag column, so the table has to read its own
 * narrative to know which row deserves the reader's eye.
 */
const FLAG_WORDS = ["異常", "注意"];

/** `split_12` -> 12; null for any other key. */
function splitNumber(key: string): number | null {
  const match = /^split_(\d+)$/.exec(key);
  return match != null ? Number(match[1]) : null;
}

/**
 * Split numbers whose narrative flags a problem (Morning Brief, #1118).
 *
 * The splits table is a wall of mono figures; without this the one kilometre
 * the analyst actually wrote a warning about looks exactly like the other
 * twenty-two. The flagged rows get the `warn` tint so the table can be scanned
 * for exceptions instead of read end to end.
 *
 * Missing / unparsed sections and non-`split_N` keys yield an empty set: a
 * table with nothing to highlight is the normal case, not an error.
 */
export function flaggedSplitIndices(
  split: SectionResult | undefined,
): Set<number> {
  const analyses = split?.data?.analyses;
  const flagged = new Set<number>();
  if (analyses == null || typeof analyses !== "object" || Array.isArray(analyses)) {
    return flagged;
  }
  for (const [key, text] of Object.entries(
    analyses as Record<string, unknown>,
  )) {
    const index = splitNumber(key);
    if (index == null || typeof text !== "string") {
      continue;
    }
    if (FLAG_WORDS.some((word) => text.includes(word))) {
      flagged.add(index);
    }
  }
  return flagged;
}
