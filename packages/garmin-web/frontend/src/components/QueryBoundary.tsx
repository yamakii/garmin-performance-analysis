import type { ReactNode } from "react";
import CardSkeleton from "./CardSkeleton";
import { ErrorPanel } from "./PageState";

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
      <ErrorPanel
        message={`${label}の読み込みに失敗しました: ${query.error.message}`}
        onRetry={() => query.refetch()}
      />
    );
  }

  if (query.data === undefined) {
    return <CardSkeleton label={label} />;
  }

  return <>{children(query.data)}</>;
}
