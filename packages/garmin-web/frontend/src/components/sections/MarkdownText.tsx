import ReactMarkdown from "react-markdown";

/** Renders Markdown-style Japanese analysis text from section JSON. */
export default function MarkdownText({ text }: { text: string }) {
  return <ReactMarkdown>{text}</ReactMarkdown>;
}
