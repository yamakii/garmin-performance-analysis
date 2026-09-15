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

/**
 * jsdom has no layout, so `scrollIntoView` is not implemented at all. It is
 * assigned (not spied on) for that reason, and removed again afterwards.
 */
function stubScrollIntoView() {
  const scrollIntoView = vi.fn();
  Element.prototype.scrollIntoView = scrollIntoView;
  return scrollIntoView;
}

afterEach(() => {
  vi.unstubAllGlobals();
  delete (Element.prototype as Partial<Element>).scrollIntoView;
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
    expect(splits).toHaveClass("font-bold");
    expect(screen.getByRole("link", { name: "総合評価" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("test_section_nav_scrolls_active_into_view", () => {
    const { callbacks } = installObserver();
    const scrollIntoView = stubScrollIntoView();
    render(
      <>
        <div id="overview" />
        <div id="split" />
        <SectionNav
          items={[
            { id: "overview", label: "総合評価" },
            { id: "split", label: "スプリット" },
          ]}
        />
      </>,
    );

    // Nothing is current yet, so the strip has not been scrolled.
    expect(scrollIntoView).not.toHaveBeenCalled();

    act(() => {
      callbacks[0]([
        {
          target: document.getElementById("split") as Element,
          isIntersecting: true,
        },
      ]);
    });

    // The item that just became current is brought into the strip — `nearest`
    // on both axes so the page itself never moves.
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
    expect(scrollIntoView).toHaveBeenCalledWith({
      block: "nearest",
      inline: "nearest",
    });
    expect(scrollIntoView.mock.contexts[0]).toBe(
      screen.getByRole("link", { name: "スプリット" }),
    );
  });

  it("test_section_nav_list_hides_vertical_overflow", () => {
    render(
      <SectionNav
        items={[
          { id: "overview", label: "総合評価" },
          { id: "split", label: "スプリット" },
          { id: "form", label: "フォーム" },
        ]}
      />,
    );

    const list = screen.getByRole("list");
    expect(list).toHaveClass("overflow-x-auto", "overflow-y-hidden");
  });

  it("test_section_nav_active_underline_is_a_pseudo_element", () => {
    const { callbacks } = installObserver();
    render(
      <>
        <div id="overview" />
        <div id="split" />
        <SectionNav
          items={[
            { id: "overview", label: "総合評価" },
            { id: "split", label: "スプリット" },
          ]}
        />
      </>,
    );

    act(() => {
      callbacks[0]([
        {
          target: document.getElementById("split") as Element,
          isIntersecting: true,
        },
      ]);
    });

    const current = screen.getByRole("link", { name: "スプリット" });
    expect(current).toHaveAttribute("aria-current", "location");
    expect(current).toHaveClass("after:h-0.5", "after:bg-ink");
    expect(current).not.toHaveClass("-mb-px", "border-b-2");
  });

  it("test_section_nav_inactive_link_has_no_underline", () => {
    render(
      <SectionNav
        items={[
          { id: "overview", label: "総合評価" },
          { id: "split", label: "スプリット" },
        ]}
      />,
    );

    const inactive = screen.getByRole("link", { name: "総合評価" });
    expect(inactive).not.toHaveClass("after:bg-ink");
  });
});
