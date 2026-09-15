import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SectionNav from "./SectionNav";

type ObserverCallback = (entries: Partial<IntersectionObserverEntry>[]) => void;

/** Installs a fake IntersectionObserver and returns its captured callbacks. */
function installObserver(): { callbacks: ObserverCallback[]; observed: string[] } {
  const callbacks: ObserverCallback[] = [];
  const observed: string[] = [];
  class FakeObserver {
    constructor(callback: ObserverCallback) {
      callbacks.push(callback);
    }
    observe(target: Element) {
      observed.push(target.id);
    }
    disconnect() {}
  }
  vi.stubGlobal("IntersectionObserver", FakeObserver);
  return { callbacks, observed };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

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
    // Nothing is current until a section has been observed.
    expect(overview).not.toHaveAttribute("aria-current");
  });

  it("renders nothing when items empty", () => {
    const { container } = render(<SectionNav items={[]} />);

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("test_section_nav_marks_current_section", () => {
    const { callbacks, observed } = installObserver();
    render(
      <>
        <div id="section-overview" />
        <div id="section-splits" />
        <SectionNav
          items={[
            { id: "section-overview", label: "総合評価" },
            { id: "section-splits", label: "スプリット" },
          ]}
        />
      </>,
    );

    // Every listed section is watched.
    expect(observed).toEqual(["section-overview", "section-splits"]);

    act(() => {
      callbacks[0]([
        {
          target: document.getElementById("section-splits") as Element,
          isIntersecting: true,
        },
      ]);
    });

    const splits = screen.getByRole("link", { name: "スプリット" });
    expect(splits).toHaveAttribute("aria-current", "location");
    expect(splits).toHaveClass("font-bold", "border-b-2");
    expect(screen.getByRole("link", { name: "総合評価" })).not.toHaveAttribute(
      "aria-current",
    );
  });
});
