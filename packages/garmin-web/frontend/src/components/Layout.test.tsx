import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import Layout from "./Layout";

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
  it("renders all four nav links", () => {
    renderLayout();

    expect(screen.getByRole("link", { name: "一覧" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "トレンド" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "目標" })).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "週次レビュー" }),
    ).toBeInTheDocument();

    // Children render inside the content container.
    expect(screen.getByText("コンテンツ")).toBeInTheDocument();

    // NavLink marks the active route with aria-current="page".
    expect(screen.getByRole("link", { name: "一覧" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("nav remains reachable at narrow width", () => {
    renderLayout();

    // Lightweight strategy: the nav scrolls horizontally instead of wrapping
    // or cramping the four links on narrow screens.
    const nav = screen.getByRole("navigation", {
      name: "メインナビゲーション",
    });
    expect(nav).toHaveClass("overflow-x-auto");

    // Links stay full-size (do not compress) so they remain tappable.
    for (const name of ["一覧", "トレンド", "目標", "週次レビュー"]) {
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
