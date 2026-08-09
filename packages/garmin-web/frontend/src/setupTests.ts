import "@testing-library/jest-dom/vitest";

/**
 * jsdom ships `window.scrollTo` as a stub that logs "Not implemented" to the
 * console. `ScrollToTop` calls it on every navigation, so without this every
 * routing test printed that error and buried the real output. Assigned rather
 * than `vi.stubGlobal`-ed so a suite's `vi.unstubAllGlobals()` restores this
 * no-op (tests that assert on scrolling stub it themselves).
 */
// Source-guard suites run in the node environment and have no window.
if (typeof window !== "undefined") {
  window.scrollTo = () => {};
}
