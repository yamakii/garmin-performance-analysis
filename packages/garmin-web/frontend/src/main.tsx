import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
// Editorial Sport faces (Issue #214) — only the weights actually used,
// to keep the bundle lean: display headings (700) + condensed KPI numerals
// (400 for units / 600 SemiBold for the big numbers).
import "@fontsource/zen-kaku-gothic-new/700.css";
import "@fontsource/barlow-condensed/400.css";
import "@fontsource/barlow-condensed/600.css";
import "./index.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element #root not found");
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
