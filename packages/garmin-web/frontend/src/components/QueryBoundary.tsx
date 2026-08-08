import type { ReactNode } from "react";
import CardSkeleton from "./CardSkeleton";

/**
 * The slice of a TanStack Query result this boundary needs. Kept structural
 * (rather than importing `UseQueryResult`) so callers can pass a plain object
 * in tests without constructing a full query result.
 */
export interface QueryLike<T> {
  data: T | undefined;
  error: Error | null;
  refetch: () => void;
}

/**
 * Per-card state switch for a fetched card: pending -> `CardSkeleton`,
 * failed -> an alert with a retry button, resolved -> `children(data)`.
 *
 * Cards render independently, so one slow or failing endpoint degrades only
 * its own card instead of holding (or blanking) the whole page. The error
 * branch wins over the pending branch: when a refetch fails while stale data
 * is still around, the failure is what the reader needs to see.
 */
export default function QueryBoundary<T>({
  label,
  query,
  children,
}: {
  /** Card name, used for the skeleton's a11y label and the error message. */
  label: string;
  query: QueryLike<T>;
  children: (data: T) => ReactNode;
}) {
  if (query.error != null) {
    return (
      <div
        role="alert"
        className="flex flex-col items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-8 text-sm text-red-700"
      >
        <p>
          {label}の読み込みに失敗しました: {query.error.message}
        </p>
        <button
          type="button"
          onClick={() => query.refetch()}
          className="rounded-lg border border-red-300 bg-white px-4 py-1.5 font-medium text-red-700 transition-colors hover:bg-red-100"
        >
          再試行
        </button>
      </div>
    );
  }

  if (query.data === undefined) {
    return <CardSkeleton label={label} />;
  }

  return <>{children(query.data)}</>;
}
