import { MemoryRouter, useNavigate } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "./test/utils";
import App, { ScrollToTop } from "./App";

// echarts requires a real canvas; mock the modular wrapper out for jsdom
vi.mock("./lib/echarts", () => ({
  echarts: {
    init: () => ({
      setOption: vi.fn(),
      resize: vi.fn(),
      dispose: vi.fn(),
    }),
  },
}));

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.pushState({}, "", "/");
});

/**
 * Fail every API call: routing is what is under test here, and each card
 * degrades to its own in-card alert instead of blanking the page, so the page
 * shell still renders.
 */
function stubFailingApi(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "unavailable" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
}

/** Two navigations to drive `ScrollToTop`: a plain one and an anchor one. */
function Navigator() {
  const navigate = useNavigate();
  return (
    <>
      <button type="button" onClick={() => navigate("/condition")}>
        go
      </button>
      <button type="button" onClick={() => navigate("/performance#form")}>
        go-anchor
      </button>
    </>
  );
}

describe("ScrollToTop", () => {
  it("test_scroll_to_top_on_navigation", () => {
    const scrollTo = vi.fn();
    vi.stubGlobal("scrollTo", scrollTo);

    render(
      <MemoryRouter initialEntries={["/activities"]}>
        <ScrollToTop />
        <Navigator />
      </MemoryRouter>,
    );

    // Only the navigation is under test, not the initial mount.
    scrollTo.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "go" }));

    expect(scrollTo).toHaveBeenCalledWith(0, 0);

    // An in-page anchor owns the scroll position: jumping to the top here
    // would undo the jump to the linked section.
    scrollTo.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "go-anchor" }));

    expect(scrollTo).not.toHaveBeenCalled();
  });
});

describe("App routing", () => {
  it("test_unknown_route_renders_not_found", async () => {
    window.history.pushState({}, "", "/no-such-page");

    render(<App />);

    // NotFound is lazy-loaded, so wait for the chunk to resolve.
    expect(
      await screen.findByText("ページが見つかりません"),
    ).toBeInTheDocument();
    // The Layout shell (and its nav) still wraps the 404 page.
    expect(
      screen.getByRole("navigation", { name: "メインナビゲーション" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "ホームへ戻る" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("test_trends_redirects_to_condition", async () => {
    stubFailingApi();
    // A stale bookmark / Home snapshot tile deep link into the retired page.
    window.history.pushState({}, "", "/trends#recovery");

    render(<App />);

    // The condition page renders in place of the retired trends dashboard...
    expect(
      await screen.findByRole("heading", { level: 1, name: "今の体の状態" }),
    ).toBeInTheDocument();
    // ...at the new URL, with the deep-link hash carried across.
    expect(window.location.pathname).toBe("/condition");
    expect(window.location.hash).toBe("#recovery");
  });

  it("test_page_titles_per_route", async () => {
    stubFailingApi();
    window.history.pushState({}, "", "/activities");

    const { unmount } = render(<App />);

    // An SPA never reloads the document, so each route has to name the tab
    // itself — otherwise every page shares one meaningless title (#912).
    await waitFor(() => {
      expect(document.title).toContain("アクティビティ");
    });
    expect(document.title).toContain("Garmin Performance");
    unmount();

    // A second route proves the title tracks navigation, not just first paint.
    window.history.pushState({}, "", "/condition");
    render(<App />);

    await waitFor(() => {
      expect(document.title).toContain("コンディション");
    });
  });
});
