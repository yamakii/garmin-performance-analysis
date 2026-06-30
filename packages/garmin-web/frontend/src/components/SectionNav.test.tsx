import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SectionNav from "./SectionNav";

describe("SectionNav", () => {
  it("renders an anchor per item", () => {
    render(
      <SectionNav
        items={[
          { id: "section-overview", label: "総合評価" },
          { id: "section-splits", label: "スプリット" },
        ]}
      />,
    );

    const overview = screen.getByRole("link", { name: "総合評価" });
    const splits = screen.getByRole("link", { name: "スプリット" });
    expect(overview).toHaveAttribute("href", "#section-overview");
    expect(splits).toHaveAttribute("href", "#section-splits");
    expect(screen.getAllByRole("link")).toHaveLength(2);
  });

  it("renders nothing when items empty", () => {
    const { container } = render(<SectionNav items={[]} />);

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
});
