import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

function navLinkClass({ isActive }: { isActive: boolean }): string {
  const base = "rounded-md px-3 py-1.5 text-sm font-medium transition-colors";
  return isActive
    ? `${base} bg-ink/5 text-ink`
    : `${base} text-slate-600 hover:bg-slate-100 hover:text-ink`;
}

/**
 * App shell: sticky white header (brand + nav with active state) and a
 * centered content container. Purely presentational.
 */
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      <header className="sticky top-0 z-[1100] border-b border-slate-200 bg-white shadow-sm">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
          <NavLink
            to="/"
            className="font-display text-lg font-bold tracking-tight text-ink"
          >
            Garmin Performance
          </NavLink>
          <nav aria-label="メインナビゲーション" className="flex gap-1">
            <NavLink to="/" end className={navLinkClass}>
              一覧
            </NavLink>
            <NavLink to="/trends" className={navLinkClass}>
              トレンド
            </NavLink>
            <NavLink to="/goal" className={navLinkClass}>
              目標
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
    </div>
  );
}
