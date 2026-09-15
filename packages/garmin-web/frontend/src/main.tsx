import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
// Morning Brief faces (Epic #1115) — only the weights the type scale uses:
// BIZ UDPGothic 400/700 for prose and headings, IBM Plex Mono 400/500/600
// for numerals, dates and labels.
import "@fontsource/biz-udpgothic/400.css";
import "@fontsource/biz-udpgothic/700.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "./index.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element #root not found");
}

// One shared cache for the whole SPA: read-only endpoints stay fresh for a
// minute (no refetch on navigation round-trips), and a single retry absorbs
// transient network blips without hammering the API.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 1,
    },
  },
});

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
