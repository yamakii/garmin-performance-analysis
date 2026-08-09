/**
 * Whole-page loading and failure states (#914).
 *
 * A route that fetches one all-or-nothing payload (the activity list, a goal,
 * a weekly review) can only be in one of three states, and every page used to
 * spell out the first two itself: six copies of the spinner markup and five
 * error banners reading `エラー: {message}` with no way out other than a manual
 * browser reload. These two components are that markup, once — so the wording
 * is uniform and a failed fetch always offers a retry.
 *
 * Per-card failures are a different problem and keep their own local handling
 * (`QueryBoundary`), because one dead card must not blank the whole page.
 */

/** Spinner + label shown while a page's primary fetch is still pending. */
export function PageLoading() {
  return (
    <div
      role="status"
      className="flex items-center justify-center gap-3 py-16 text-sm text-slate-500"
    >
      {/* Decorative: the adjacent text is what gets announced. The animation
          is dropped under prefers-reduced-motion. */}
      <span
        aria-hidden="true"
        className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-ink motion-reduce:animate-none"
      />
      読み込み中...
    </div>
  );
}

/**
 * Page-level fetch failure: what failed, why, and a button to try again.
 *
 * `onRetry` is the query's `refetch` — a retry that re-runs the request in
 * place, so a transient 500 or a dropped connection costs one click instead of
 * a full page reload.
 */
export function PageError({
  error,
  onRetry,
}: {
  error: Error;
  onRetry: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-8 text-sm text-red-700"
    >
      <p>読み込みに失敗しました: {error.message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="rounded-lg border border-red-300 bg-white px-4 py-1.5 font-medium text-red-700 transition-colors hover:bg-red-100"
      >
        再試行
      </button>
    </div>
  );
}
