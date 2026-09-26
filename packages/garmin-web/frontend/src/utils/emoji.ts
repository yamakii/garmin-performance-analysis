/**
 * What counts as emoji on this site (#1428), the same set as the server's
 * `garmin_mcp.validation.pictographs.PICTOGRAPH_RE`.
 *
 * The design system states verdicts in words or the `✓` / `!` glyphs, never
 * emoji (#1186 / #1187 / #1188). This matches what renders as an emoji: the
 * supplementary pictograph planes, the emoji variation selector U+FE0F and
 * the BMP characters whose default presentation is emoji. `✓`, `!`, the
 * legacy `★☆` stars and a bare text `⚠` do not match. U+FE0F sits outside the
 * class: inside one it would pair with the previous character
 * (`no-misleading-character-class`).
 *
 * The tests use it to keep emoji out of the DOM and out of the source; the
 * only file allowed to spell a verdict mark is `verdictRating.ts`, which maps
 * the stored `rating` key to its word.
 */
export const PICTOGRAPH_RE =
  /\u{FE0F}|[\u{1F000}-\u{1FAFF}\u{231A}-\u{231B}\u{23E9}-\u{23EC}\u{23F0}\u{23F3}\u{25FD}-\u{25FE}\u{2614}-\u{2615}\u{2648}-\u{2653}\u{267F}\u{2693}\u{26A1}\u{26AA}-\u{26AB}\u{26BD}-\u{26BE}\u{26C4}-\u{26C5}\u{26CE}\u{26D4}\u{26EA}\u{26F2}-\u{26F3}\u{26F5}\u{26FA}\u{26FD}\u{2705}\u{270A}-\u{270B}\u{2728}\u{274C}\u{274E}\u{2753}-\u{2755}\u{2757}\u{2795}-\u{2797}\u{27B0}\u{27BF}\u{2B1B}-\u{2B1C}\u{2B50}\u{2B55}]/u;
