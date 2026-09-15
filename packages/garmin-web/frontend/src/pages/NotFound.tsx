import { Link } from "react-router-dom";
import { usePageTitle } from "../hooks/usePageTitle";

/**
 * Catch-all page for unknown URLs. Rendered inside the app Layout so the header
 * nav stays available, which keeps a mistyped or stale link one click away from
 * a real page instead of a blank screen.
 */
export default function NotFound() {
  usePageTitle("ページが見つかりません");
  return (
    <div className="flex flex-col items-center gap-3 py-20 text-center">
      {/*
       * Decorative-scale numeral, but still real text: slate-300 (1.48:1) and
       * slate-400 (2.63:1) both miss even the 3:1 large-text floor, so the 404
       * uses slate-500 (4.77:1) — Issue #911.
       */}
      <p className="font-mono text-5xl font-bold text-ink-muted">404</p>
      <h1 className="text-xl font-semibold text-ink">
        ページが見つかりません
      </h1>
      <p className="text-sm text-ink-muted">
        URL が変わったか、削除された可能性があります。
      </p>
      <Link
        to="/"
        className="mt-2 rounded-md border border-hairline px-4 py-1.5 text-sm font-medium text-ink transition-colors hover:bg-surface"
      >
        ホームへ戻る
      </Link>
    </div>
  );
}
