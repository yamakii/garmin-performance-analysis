import type { JSX } from "react";
import ReactMarkdown, { type Components } from "react-markdown";

/**
 * Inline mode drops the paragraph wrapper (#1150): the coach's sentences are
 * written with `**強調**` but live inside the caller's own element — a
 * `CoachNote` rule, a `<p>`, an `<li>` — where a block `<p>` would add margins
 * and change the DOM shape the plain-text version had.
 */
const INLINE_COMPONENTS: Components = {
  p: ({ children }) => <>{children}</>,
};

/** Renders Markdown-style Japanese analysis text from section JSON. */
export default function MarkdownText({
  children,
  inline = false,
  className,
}: {
  children: string;
  /** Render the markdown in the caller's flow, without a block wrapper. */
  inline?: boolean;
  className?: string;
}): JSX.Element {
  if (inline) {
    const body = (
      <ReactMarkdown components={INLINE_COMPONENTS}>{children}</ReactMarkdown>
    );
    return className != null ? <span className={className}>{body}</span> : body;
  }
  return (
    <div
      className={`markdown-body text-sm leading-relaxed text-ink-soft${
        className != null ? ` ${className}` : ""
      }`}
    >
      <ReactMarkdown>{children}</ReactMarkdown>
    </div>
  );
}
