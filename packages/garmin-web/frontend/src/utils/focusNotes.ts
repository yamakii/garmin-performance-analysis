/**
 * Parse `focus_notes` (a free-text string written by the `/set-goal` CLI) into
 * titled sections for the goal page's structured accordion.
 *
 * Convention (soft contract, see `.claude/commands/set-goal.md`):
 *   `【見出し】本文【見出し2】本文2`
 *
 * Rules:
 * - `null` / empty (after trim) → `[]`
 * - Each `【…】` starts a new section; its `title` is the bracket text and
 *   `body` is the trimmed text up to the next `【` (or end).
 * - Any preamble before the first `【` becomes `{ title: null, body }`.
 * - If there is no `【…】` at all, the whole string is returned as a single
 *   `{ title: null, body }` element. This fallback keeps the UI intact when
 *   the source data does not follow the convention.
 */
export type FocusSection = { title: string | null; body: string };

const HEADING_RE = /【(.+?)】/g;

export function parseFocusNotes(notes: string | null): FocusSection[] {
  if (notes == null) {
    return [];
  }
  const trimmed = notes.trim();
  if (trimmed === "") {
    return [];
  }

  const matches = [...trimmed.matchAll(HEADING_RE)];

  // Fallback: no 【…】 headings → single untitled section with the full text.
  if (matches.length === 0) {
    return [{ title: null, body: trimmed }];
  }

  const sections: FocusSection[] = [];

  // Preamble before the first heading.
  const firstStart = matches[0].index ?? 0;
  const preamble = trimmed.slice(0, firstStart).trim();
  if (preamble !== "") {
    sections.push({ title: null, body: preamble });
  }

  matches.forEach((match, i) => {
    const title = match[1].trim();
    const bodyStart = (match.index ?? 0) + match[0].length;
    const bodyEnd = i + 1 < matches.length ? matches[i + 1].index : undefined;
    const body = trimmed.slice(bodyStart, bodyEnd).trim();
    sections.push({ title, body });
  });

  return sections;
}
