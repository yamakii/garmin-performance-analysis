import { useEffect, useRef, useState, type JSX } from "react";

export interface NavItem {
  id: string;
  label: string;
}

/**
 * How far below the top of the viewport a section has to reach before it
 * counts as the current one: the sticky nav's own height, then most of the
 * viewport so the section actually being read (not the one about to leave)
 * wins.
 */
const OBSERVER_ROOT_MARGIN = "-60px 0px -70% 0px";

/**
 * Sticky in-page table of contents for the long vertical reports
 * (ActivityDetail / Performance / WeeklyReviewDetail). Callers pass only the
 * sections that are actually rendered, so the nav never points at a missing
 * anchor. Each target section carries `scroll-mt-[60px]` so the sticky bar
 * does not cover the heading after a jump. Renders nothing when there is
 * nothing to link.
 *
 * The current section is tracked with an IntersectionObserver and marked as
 * `aria-current="location"` plus the same underline the main nav uses. jsdom
 * has no IntersectionObserver, so the tracking is simply skipped there.
 */
export default function SectionNav({
  items,
}: {
  items: NavItem[];
}): JSX.Element | null {
  const [current, setCurrent] = useState<string | null>(null);
  const links = useRef(new Map<string, HTMLAnchorElement>());
  const idsKey = items.map((item) => item.id).join("|");

  useEffect(() => {
    if (idsKey === "" || typeof IntersectionObserver === "undefined") {
      return;
    }
    const ids = idsKey.split("|");
    const visible = new Set<string>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            visible.add(entry.target.id);
          } else {
            visible.delete(entry.target.id);
          }
        }
        // The topmost visible section (in document order) is the current one.
        const first = ids.find((id) => visible.has(id));
        if (first != null) {
          setCurrent(first);
        }
      },
      { rootMargin: OBSERVER_ROOT_MARGIN },
    );
    for (const id of ids) {
      const target = document.getElementById(id);
      if (target != null) {
        observer.observe(target);
      }
    }
    return () => observer.disconnect();
  }, [idsKey]);

  // The list scrolls sideways when the sections do not fit, so the section
  // being read can end up marked as current while sitting outside the strip.
  // `nearest` scrolls the strip only as far as it has to, and never the page.
  // jsdom has no layout and therefore no scrollIntoView, so guard on it the
  // same way the observer above is guarded.
  useEffect(() => {
    if (current == null) {
      return;
    }
    const link = links.current.get(current);
    if (typeof link?.scrollIntoView === "function") {
      link.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }, [current]);

  if (items.length === 0) {
    return null;
  }
  return (
    <nav
      aria-label="セクション目次"
      className="sticky top-0 z-20 border-b border-hairline bg-paper"
    >
      <ul className="flex gap-5 overflow-x-auto overflow-y-hidden text-sm">
        {items.map((item) => {
          const isCurrent = item.id === current;
          return (
            <li key={item.id} className="shrink-0">
              <a
                href={`#${item.id}`}
                ref={(node) => {
                  if (node == null) {
                    links.current.delete(item.id);
                  } else {
                    links.current.set(item.id, node);
                  }
                }}
                aria-current={isCurrent ? "location" : undefined}
                className={`relative block pt-2.5 pb-3 whitespace-nowrap hover:text-ink hover:no-underline ${
                  isCurrent
                    ? "font-bold text-ink after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:bg-ink"
                    : "text-ink-muted"
                }`}
              >
                {item.label}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
