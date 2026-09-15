/**
 * The shell every content block on the app wears (#914, restyled for Morning
 * Brief in #1116).
 *
 * A block is no longer a white card with a shadow: it is a hairline rule and
 * the whitespace under it. Import the constant instead of retyping the class
 * list; extra classes compose around it:
 *
 * ```tsx
 * <section className={CARD_CLASS} />
 * <section className={`scroll-mt-[60px] ${CARD_CLASS}`} />
 * ```
 *
 * `Card.test.ts` fails if the retired decoration classes (large radii, shadows,
 * gradients, the old display / numeric faces, raw slate hues) reappear
 * anywhere under `src/`.
 */
export const CARD_CLASS = "border-t border-hairline pt-4";
