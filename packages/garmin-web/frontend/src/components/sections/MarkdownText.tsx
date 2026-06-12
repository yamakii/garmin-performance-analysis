import ReactMarkdown from "react-markdown";

/** Renders Markdown-style Japanese analysis text from section JSON. */
export default function MarkdownText({ text }: { text: string }) {
  return (
    <div className="markdown-body text-sm leading-relaxed text-slate-700">
      <ReactMarkdown>{text}</ReactMarkdown>
    </div>
  );
}
