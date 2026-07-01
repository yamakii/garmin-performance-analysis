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
 * so all five links stay reachable without wrapping or cramping on ~360px
 * screens.
 */
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
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
            <NavLink to="/trends" className={navLinkClass}>
              トレンド
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
      <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
    </div>
  );
}
