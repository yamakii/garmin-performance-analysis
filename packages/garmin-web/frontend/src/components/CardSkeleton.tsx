/**
 * Card-shaped loading placeholder shown while a TrendsDashboard card's data is
 * still resolving. It mirrors the card shell (`rounded-xl border ... shadow-sm`)
 * so the real card drops in without a layout shift once its fetch resolves.
 *
 * The pulsing bars use `animate-pulse`, which is disabled under
 * `prefers-reduced-motion` via `motion-reduce:animate-none`. The element is a
 * `role="status"` / `aria-busy="true"` region so assistive tech announces the
 * card as loading; `label` lets the caller name which card is pending.
 */
export default function CardSkeleton({ label }: { label?: string }) {
  return (
    <section
      role="status"
      aria-busy="true"
      aria-label={label ?? "読み込み中"}
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="animate-pulse space-y-3 motion-reduce:animate-none">
        <div className="h-4 w-1/3 rounded bg-slate-200" />
        <div className="h-3 w-2/3 rounded bg-slate-100" />
        <div className="h-40 w-full rounded bg-slate-100" />
      </div>
      <span className="sr-only">読み込み中</span>
    </section>
  );
}
