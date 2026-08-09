import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

function navLinkClass({ isActive }: { isActive: boolean }): string {
  const base =
    "shrink-0 whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium transition-colors";
  return isActive
    ? `${base} bg-ink/5 text-ink`
    : `${base} text-slate-600 hover:bg-slate-100 hover:text-ink`;
}

/**
 * App shell: sticky white header (brand + nav with active state) and a
 * centered content container. Purely presentational.
 *
 * Narrow-width strategy (#652): the brand shrinks to "Garmin" below the `sm`
 * breakpoint and the nav becomes horizontally scrollable (`overflow-x-auto`)
 * so all six links stay reachable without wrapping or cramping on ~360px
 * screens.
 *
 * The skip link is the first focusable element on every page (WCAG 2.4.1): it
 * is visually hidden until focused, and jumps past the six nav links straight
 * to `#main`, which takes focus itself (`tabIndex={-1}`) so the next Tab
 * continues inside the content.
 */
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-4 focus:z-[1200] focus:rounded-md focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-ink focus:shadow-md focus:ring-2 focus:ring-signal/50"
      >
        本文へスキップ
      </a>
      <header className="sticky top-0 z-[1100] border-b border-slate-200 bg-white shadow-sm">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-3 px-4">
          <NavLink
            to="/"
            aria-label="Garmin Performance ホーム"
            className="shrink-0 font-display text-lg font-bold tracking-tight text-ink"
          >
            <span className="sm:hidden">Garmin</span>
            <span className="hidden sm:inline">Garmin Performance</span>
          </NavLink>
          <nav
            aria-label="メインナビゲーション"
            className="flex min-w-0 flex-1 justify-end gap-1 overflow-x-auto"
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
            <NavLink to="/weekly-reviews" className={navLinkClass}>
              週次レビュー
            </NavLink>
          </nav>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="mx-auto max-w-5xl px-4 py-6">
        {children}
      </main>
    </div>
  );
}
