import type { JSX } from "react";

/**
 * Editorial section heading: an uppercase English eyebrow stacked above a
 * Japanese heading, matching the "Editorial Sport" pattern that previously
 * lived only on the Goal page. Use `as="h1"` (default) for the page headline
 * and `as="h2"` for in-page section headers — the eyebrow stays the same while
 * the heading scales from `text-2xl` to `text-xl`.
 */
export default function SectionHeading({
  eyebrow,
  title,
  as = "h1",
}: {
  eyebrow: string;
  title: string;
  as?: "h1" | "h2";
}): JSX.Element {
  const Heading = as;
  const titleSize = as === "h1" ? "text-2xl" : "text-xl";
  return (
    <div>
      <p className="text-xs font-semibold tracking-[0.2em] text-slate-400 uppercase">
        {eyebrow}
      </p>
      <Heading
        className={`mt-1 font-display ${titleSize} font-bold tracking-tight text-ink`}
      >
        {title}
      </Heading>
    </div>
  );
}
