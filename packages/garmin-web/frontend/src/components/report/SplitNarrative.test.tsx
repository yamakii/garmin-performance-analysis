import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SplitNarrative from "./SplitNarrative";

describe("SplitNarrative", () => {
  it("renders dynamic split keys in order", () => {
    const section = {
      data: {
        metadata: {
          activity_id: "9000000101",
          date: "2025-10-09",
          analyst: "split-section-analyst",
          version: "1.0",
          timestamp: "2025-10-09T12:00:00+09:00",
        },
        highlights: "2km地点で最速ペース 6:19/km を記録しました。",
        // Intentionally unordered keys; rendering must sort numerically.
        analyses: {
          split_3: "3km目は心拍が上がり気味でした。",
          split_1: "入りの1kmは抑えた立ち上がりでした。",
          split_2: "2km目でペースが安定しました。",
        },
      },
      parse_error: false,
      raw: null,
    };

    render(<SplitNarrative section={section} />);

    expect(
      screen.getByText("2km地点で最速ペース 6:19/km を記録しました。"),
    ).toBeInTheDocument();

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("入りの1kmは抑えた立ち上がりでした。");
    expect(items[1]).toHaveTextContent("2km目でペースが安定しました。");
    expect(items[2]).toHaveTextContent("3km目は心拍が上がり気味でした。");

    // Number badges are derived from the dynamic split_N keys
    expect(screen.getByLabelText("スプリット 1")).toHaveTextContent("1");
    expect(screen.getByLabelText("スプリット 3")).toHaveTextContent("3");
  });

  it("test_split_narrative_collapsed_by_default", () => {
    const analyses = Object.fromEntries(
      Array.from({ length: 10 }, (_, i) => [
        `split_${i + 1}`,
        `${i + 1}km目の解説テキストです。`,
      ]),
    );
    render(
      <SplitNarrative
        section={{
          data: {
            highlights: "2km地点で最速ペース 6:19/km を記録しました。",
            analyses,
          },
          parse_error: false,
          raw: null,
        }}
      />,
    );

    // highlights stays visible: it is already the 60-120 character summary.
    const highlights = screen.getByText(
      "2km地点で最速ペース 6:19/km を記録しました。",
    );
    expect(highlights.closest("details")).toBeNull();

    // Every per-split line is folded away behind a collapsed disclosure...
    const details = screen.getByText("スプリット別の解説").closest("details");
    expect(details).not.toBeNull();
    expect(details?.hasAttribute("open")).toBe(false);

    // ...and all ten lines are there once it is expanded.
    const items = within(details as HTMLElement).getAllByRole("listitem");
    expect(items).toHaveLength(10);
    expect(items[9]).toHaveTextContent("10km目の解説テキストです。");
  });

  it("renders nothing when the section is missing", () => {
    const { container } = render(<SplitNarrative section={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });
});
