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
  "週次レビュー",
];

function renderLayout(initialPath = "/") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Layout>
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

  it("nav remains reachable at narrow width", () => {
    renderLayout();

    // Lightweight strategy: the nav scrolls horizontally instead of wrapping
    // or cramping the five links on narrow screens.
    const nav = screen.getByRole("navigation", {
      name: "メインナビゲーション",
    });
    expect(nav).toHaveClass("overflow-x-auto");

    // Links stay full-size (do not compress) so they remain tappable.
    for (const name of NAV_LINKS) {
      expect(screen.getByRole("link", { name })).toHaveClass("shrink-0");
    }
  });

  it("brand link points to root", () => {
    renderLayout();

    const brand = screen.getByRole("link", {
      name: "Garmin Performance ホーム",
    });
    expect(brand).toHaveAttribute("href", "/");
  });
});
