import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import Layout from "./Layout";

const NAV_LINKS = [
  "ホーム",
  "アクティビティ",
  "コンディション",
  "パフォーマンス",
  "目標",
  "計画",
];

function renderLayout(initialPath = "/") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Layout today={new Date(2026, 8, 15)}>
        <p>コンテンツ</p>
      </Layout>
    </MemoryRouter>,
  );
}

describe("Layout", () => {
  it("test_nav_has_six_items", () => {
    renderLayout();

    const nav = screen.getByRole("navigation", { name: "メインナビゲーション" });
    // Exactly the six IA destinations (#892): the split of トレンド into
    // コンディション / パフォーマンス leaves no トレンド link behind.
    expect(within(nav).getAllByRole("link")).toHaveLength(NAV_LINKS.length);
    for (const name of NAV_LINKS) {
      expect(within(nav).getByRole("link", { name })).toBeInTheDocument();
    }
    expect(screen.queryByRole("link", { name: "トレンド" })).toBeNull();
    // 計画 took the sixth slot from 週次レビュー (#983), which is now reached
    // from the grid instead of the nav.
    expect(within(nav).getByRole("link", { name: "計画" })).toHaveAttribute(
      "href",
      "/plan",
    );
    expect(screen.queryByRole("link", { name: "週次レビュー" })).toBeNull();

    // Children render inside the content container.
    expect(screen.getByText("コンテンツ")).toBeInTheDocument();

    // NavLink marks the active route with aria-current="page".
    expect(screen.getByRole("link", { name: "ホーム" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("marks コンディション active on the /condition route", () => {
    renderLayout("/condition");

    expect(screen.getByRole("link", { name: "コンディション" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      screen.getByRole("link", { name: "パフォーマンス" }),
    ).not.toHaveAttribute("aria-current");
  });

  it("marks アクティビティ active on the /activities route", () => {
    renderLayout("/activities");

    expect(screen.getByRole("link", { name: "アクティビティ" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "ホーム" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("test_layout_header_date_and_wrap_nav", () => {
    renderLayout();

    // The nav wraps at narrow widths instead of scrolling sideways (#1116).
    const nav = screen.getByRole("navigation", {
      name: "メインナビゲーション",
    });
    expect(nav).toHaveClass("flex-wrap");
    expect(nav).not.toHaveClass("overflow-x-auto");

    // The active link is the underlined bold one; the others stay muted.
    expect(screen.getByRole("link", { name: "ホーム" })).toHaveClass(
      "font-bold",
      "border-b-2",
    );
    expect(screen.getByRole("link", { name: "目標" })).toHaveClass(
      "text-ink-muted",
    );

    // Today's date sits at the right of the brand row as `YYYY-MM-DD DDD`.
    expect(screen.getByText("2026-09-15 TUE")).toHaveClass("font-mono");
  });

  it("test_skip_link_first_focusable", () => {
    renderLayout();

    // Before the brand and the six nav links: a keyboard user reaches the
    // content in one Tab instead of eight (#912).
    const first = screen.getAllByRole("link")[0];
    expect(first).toHaveTextContent("本文へスキップ");
    expect(first).toHaveAttribute("href", "#main");

    // ...and the target exists and can take focus.
    const main = screen.getByRole("main");
    expect(main).toHaveAttribute("id", "main");
    expect(main).toHaveAttribute("tabindex", "-1");
  });

  it("brand link points to root", () => {
    renderLayout();

    const brand = screen.getByRole("link", {
      name: "Garmin Performance ホーム",
    });
    expect(brand).toHaveAttribute("href", "/");
  });
});
