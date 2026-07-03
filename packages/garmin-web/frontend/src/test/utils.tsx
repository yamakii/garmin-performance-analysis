import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  render as rtlRender,
  type RenderOptions,
} from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";

/**
 * A QueryClient tuned for tests: retries are disabled so a rejected fetch
 * surfaces as an error synchronously (no exponential backoff to wait out), and
 * nothing is cached across tests.
 */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
    },
  });
}

/**
 * Drop-in replacement for Testing Library's `render` that wraps the tree in a
 * fresh `QueryClientProvider`. Re-exports the rest of `@testing-library/react`
 * so tests import everything (screen, within, fireEvent, waitFor, …) from here.
 */
export function render(
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper">,
) {
  const client = createTestQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
  }
  return rtlRender(ui, { wrapper: Wrapper, ...options });
}

export * from "@testing-library/react";
