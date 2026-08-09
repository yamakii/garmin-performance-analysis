/**
 * The white card shell every content card on the app wears (#914).
 *
 * The literal used to be copy-pasted into ~25 call sites, so a single tweak to
 * the border, radius or padding meant editing two dozen files and hoping none
 * was missed — the cards had drifted apart before. Import the constant instead
 * of retyping the class list; extra classes compose around it:
 *
 * ```tsx
 * <section className={CARD_CLASS} />
 * <section className={`scroll-mt-20 ${CARD_CLASS}`} />
 * ```
 *
 * `Card.test.ts` fails if the raw string reappears anywhere else under `src/`.
 */
export const CARD_CLASS =
  "rounded-xl border border-slate-200 bg-white p-5 shadow-sm";
