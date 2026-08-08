import { afterEach, describe, expect, it } from "vitest";
import { render, screen } from "./test/utils";
import App from "./App";

afterEach(() => {
  window.history.pushState({}, "", "/");
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
});
