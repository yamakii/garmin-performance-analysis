import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import Layout from "./Layout";

describe("Layout", () => {
  it("Layout renders nav links with active state", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Layout>
          <p>コンテンツ</p>
        </Layout>
      </MemoryRouter>,
    );

    const listLink = screen.getByRole("link", { name: "一覧" });
    const trendsLink = screen.getByRole("link", { name: "トレンド" });
    expect(listLink).toBeInTheDocument();
    expect(trendsLink).toBeInTheDocument();

    // NavLink marks the active route with aria-current="page"
    expect(listLink).toHaveAttribute("aria-current", "page");
    expect(trendsLink).not.toHaveAttribute("aria-current");

    // Children are rendered inside the content container
    expect(screen.getByText("コンテンツ")).toBeInTheDocument();
  });
});
