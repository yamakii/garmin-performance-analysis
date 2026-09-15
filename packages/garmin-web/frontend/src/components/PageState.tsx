/**
 * Whole-page loading and failure states (#914), restyled for Morning Brief
 * (#1116).
 *
 * A route that fetches one all-or-nothing payload (the activity list, a goal,
 * a weekly review) can only be in one of three states, and every page used to
 * spell out the first two itself. These components are that markup, once — so
 * the wording is uniform and a failed fetch always offers a retry.
 *
 * Per-card failures are a different problem and keep their own local handling
 * (`QueryBoundary`), because one dead card must not blank the whole page —
 * but they share `ErrorPanel` so every failure looks the same.
 */

/** Secondary button: an ink outline, used for "再試行" and month paging. */
export const SECONDARY_BUTTON_CLASS =
  "inline-block rounded-sm border border-ink px-3 py-[7px] text-[13px] font-bold text-ink transition-colors hover:bg-surface";

/** Label shown while a page's primary fetch is still pending. */
export function PageLoading() {
  return (
    <div
      role="status"
      className="py-16 text-center font-mono text-sm text-ink-muted"
    >
      読み込み中…
    </div>
  );
}

/**
 * A fetch failure with a retry: the one tinted block the system allows for
 * 悪. `message` is the full sentence ("走行量の読み込みに失敗しました: 500").
 */
export function ErrorPanel({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-bad-line bg-bad-tint px-4 py-3 text-sm text-status-bad"
    >
      <p>{message}</p>
      <button type="button" onClick={onRetry} className={SECONDARY_BUTTON_CLASS}>
        再試行
      </button>
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
    <ErrorPanel
      message={`読み込みに失敗しました: ${error.message}`}
      onRetry={onRetry}
    />
  );
}
