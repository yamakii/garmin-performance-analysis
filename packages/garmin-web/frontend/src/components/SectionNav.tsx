import type { JSX } from "react";

export interface NavItem {
  id: string;
  label: string;
}

/**
 * Sticky in-page table of contents for the long vertical reports
 * (ActivityDetail / WeeklyReviewDetail). Callers pass only the sections that
 * are actually rendered, so the nav never points at a missing anchor. The
 * chips scroll horizontally to stay usable on narrow screens, and each target
 * section carries `scroll-mt-*` so the sticky bar does not cover the heading
 * after a jump. Renders nothing when there is nothing to link.
 */
export default function SectionNav({
  items,
}: {
  items: NavItem[];
}): JSX.Element | null {
  if (items.length === 0) {
    return null;
  }
  return (
    <nav
      aria-label="セクション目次"
      className="sticky top-0 z-20 -mx-1 rounded-xl border border-slate-200 bg-white/90 px-2 py-2 shadow-sm backdrop-blur"
    >
      <ul className="flex gap-1.5 overflow-x-auto">
        {items.map((item) => (
          <li key={item.id} className="shrink-0">
            <a
              href={`#${item.id}`}
              className="block rounded-full px-3 py-1 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-ink"
            >
              {item.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
