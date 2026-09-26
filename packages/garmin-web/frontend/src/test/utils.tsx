import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  render as rtlRender,
  type RenderOptions,
} from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { expect } from "vitest";
import { PICTOGRAPH_RE } from "../utils/emoji";

/**
 * Assert that no emoji reached the rendered DOM (#1428): verdicts are words or
 * the `✓` / `!` glyphs. Reads the text and every attribute, so an emoji in an
 * `aria-label` or `title` fails too.
 */
export function expectNoPictographs(container: Element): void {
  const found: string[] = [];
  const text = container.textContent ?? "";
  if (PICTOGRAPH_RE.test(text)) {
    found.push(`text: ${text.slice(0, 120)}`);
  }
  for (const el of [container, ...Array.from(container.querySelectorAll("*"))]) {
    for (const attr of Array.from(el.attributes)) {
      if (PICTOGRAPH_RE.test(attr.value)) {
        found.push(`<${el.tagName.toLowerCase()} ${attr.name}="${attr.value}">`);
      }
    }
  }
  expect(found, "emoji reached the DOM").toEqual([]);
}

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
