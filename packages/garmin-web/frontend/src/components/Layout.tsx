import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { formatHeaderDate } from "../utils/format";

function navLinkClass({ isActive }: { isActive: boolean }): string {
  const base =
    "flex items-center pt-1.5 pb-2.5 transition-colors hover:text-ink hover:no-underline";
  return isActive
    ? `${base} -mb-px border-b-2 border-ink font-bold text-ink`
    : `${base} text-ink-muted`;
}

/**
 * App shell (Morning Brief, #1116): a two-row header — brand with today's
 * date on the first row, the six nav links on the second — over a centred
 * 880px column. Purely presentational.
 *
 * The header is a hairline rule, not a sticky white bar: the page reads like a
 * printed brief, and the in-page `SectionNav` is the only thing that sticks.
 * The nav wraps instead of scrolling sideways so all six links stay reachable
 * on a narrow screen without a hidden overflow.
 *
 * The skip link is the first focusable element on every page (WCAG 2.4.1): it
 * is visually hidden until focused, and jumps past the six nav links straight
 * to `#main`, which takes focus itself (`tabIndex={-1}`) so the next Tab
 * continues inside the content.
 */
export default function Layout({
  children,
  today = new Date(),
}: {
  children: ReactNode;
  /** Injectable clock for tests. */
  today?: Date;
}) {
  return (
    <div className="min-h-screen bg-paper text-ink">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-4 focus:z-[1200] focus:rounded-sm focus:border focus:border-ink focus:bg-paper focus:px-3 focus:py-2 focus:text-sm focus:font-bold focus:text-ink"
      >
        本文へスキップ
      </a>
      <header className="border-b border-hairline">
        <div className="mx-auto flex min-h-[52px] max-w-[880px] flex-wrap items-center gap-x-6 px-6">
          <NavLink
            to="/"
            aria-label="Garmin Performance ホーム"
            className="shrink-0 py-3.5 text-[15px] font-bold tracking-[-0.01em] text-ink hover:no-underline"
          >
            Garmin Performance
          </NavLink>
          <span className="order-1 ml-auto shrink-0 py-3.5 font-mono text-xs text-ink-muted">
            {formatHeaderDate(today)}
          </span>
          <nav
            aria-label="メインナビゲーション"
            className="order-2 -mt-1.5 flex basis-full flex-wrap gap-x-5 text-sm"
          >
            <NavLink to="/" end className={navLinkClass}>
              ホーム
            </NavLink>
            <NavLink to="/activities" className={navLinkClass}>
              アクティビティ
            </NavLink>
            <NavLink to="/condition" className={navLinkClass}>
              コンディション
            </NavLink>
            <NavLink to="/performance" className={navLinkClass}>
              パフォーマンス
            </NavLink>
            <NavLink to="/goal" className={navLinkClass}>
              目標
            </NavLink>
            {/* The month grid replaced the review list here (#983): the list
                was only an index over weeks, which the grid now is. Both
                review routes stay reachable from the grid. */}
            <NavLink to="/plan" className={navLinkClass}>
              計画
            </NavLink>
          </nav>
        </div>
      </header>
      <main
        id="main"
        tabIndex={-1}
        className="mx-auto flex max-w-[880px] flex-col gap-12 px-6 pt-10 pb-24"
      >
        {children}
      </main>
    </div>
  );
}
