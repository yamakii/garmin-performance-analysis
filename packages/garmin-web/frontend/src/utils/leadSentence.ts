/**
 * Split Japanese analysis prose into its opening sentence and the rest.
 *
 * The section agents write conclusion-first (`analysis-standards.md`), so the
 * first sentence carries the verdict and the remainder carries the supporting
 * detail. A visual-first layout shows the verdict as a lead line and folds the
 * rest into a clamp, which needs exactly this split.
 *
 * Sentences end at the Japanese full stop `。`; text without one is treated as
 * a single lead sentence with an empty body (never dropped).
 */
export interface LeadAndBody {
  lead: string;
  body: string;
}

export function splitLead(text: string): LeadAndBody {
  const trimmed = text.trim();
  const end = trimmed.indexOf("。");
  if (end === -1) {
    return { lead: trimmed, body: "" };
  }
  return {
    lead: trimmed.slice(0, end + 1),
    body: trimmed.slice(end + 1).trim(),
  };
}
