import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import Layout from "./Layout";

const NAV_LINKS = [
  "ホーム",
  "アクティビティ",
  "トレンド",
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
  it("renders all five nav links", () => {
    renderLayout();

    for (const name of NAV_LINKS) {
      expect(screen.getByRole("link", { name })).toBeInTheDocument();
    }

    // Children render inside the content container.
    expect(screen.getByText("コンテンツ")).toBeInTheDocument();

    // NavLink marks the active route with aria-current="page".
    expect(screen.getByRole("link", { name: "ホーム" })).toHaveAttribute(
      "aria-current",
      "page",
    );
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
