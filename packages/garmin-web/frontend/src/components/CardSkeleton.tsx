import { CARD_CLASS } from "./Card";

/**
 * Loading placeholder shown while a block's data is still resolving: the
 * block's hairline rule and a mono "——" where the number will land, so the
 * real block drops in without a layout shift. No pulse animation — the page
 * is a quiet brief, and a static dash reads as "not yet" on its own.
 *
 * The element is a `role="status"` / `aria-busy="true"` region so assistive
 * tech announces the block as loading; `label` lets the caller name which
 * block is pending.
 */
export default function CardSkeleton({ label }: { label?: string }) {
  return (
    <section
      role="status"
      aria-busy="true"
      aria-label={label ?? "読み込み中"}
      className={CARD_CLASS}
    >
      <p
        aria-hidden="true"
        className="font-mono text-[28px] leading-none text-metric-compare tracking-[0.1em]"
      >
        ——
      </p>
      <span className="sr-only">読み込み中</span>
    </section>
  );
}
