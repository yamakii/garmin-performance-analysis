import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SectionCard from "./SectionCard";

describe("SectionCard", () => {
  it("falls back to key-value for unknown fields", () => {
    const section = {
      data: {
        metadata: {
          activity_id: "9000000101",
          date: "2025-10-09",
          analyst: "summary-section-analyst",
          version: "1.0",
          timestamp: "2025-10-09T12:00:00+09:00",
        },
        // Known fields -> dedicated rendering
        star_rating: "★★★★☆ 4.3/5.0",
        summary: "有酸素ベースの安定したランでした。",
        key_strengths: ["心拍の安定", "ケイデンス維持"],
        // Unknown fields (added without version bump) -> key-value fallback
        next_action: "次回はHR 135-145でイージーランを実施",
        integrated_score: 4.1,
      },
      parse_error: false,
      raw: null,
    };

    render(<SectionCard sectionType="summary" section={section} />);

    // Known fields are rendered by the dedicated card UI
    expect(
      screen.getByRole("heading", { level: 3, name: /★★★★☆ 4.3\/5.0/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("有酸素ベースの安定したランでした。"),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 4, name: "強み" }))
      .toBeInTheDocument();
    expect(screen.getByText("心拍の安定")).toBeInTheDocument();

    // Unknown fields fall back to key-value rendering
    expect(screen.getByText("next_action")).toBeInTheDocument();
    expect(
      screen.getByText("次回はHR 135-145でイージーランを実施"),
    ).toBeInTheDocument();
    expect(screen.getByText("integrated_score")).toBeInTheDocument();
    expect(screen.getByText("4.1")).toBeInTheDocument();

    // metadata is a known boilerplate field and is not dumped as key-value
    expect(screen.queryByText("metadata")).not.toBeInTheDocument();
  });

  it("renders unknown structure without crashing via fallback", () => {
    const section = {
      data: { metadata: { activity_id: "99999999" }, test: "テストデータ" },
      parse_error: false,
      raw: null,
    };

    render(<SectionCard sectionType="mystery" section={section} />);

    expect(screen.getByText("test")).toBeInTheDocument();
    expect(screen.getByText("テストデータ")).toBeInTheDocument();
  });

  it("shows raw text when JSON parsing failed", () => {
    const section = {
      data: null,
      parse_error: true,
      raw: '{"metadata": broken',
    };

    render(<SectionCard sectionType="environment" section={section} />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText('{"metadata": broken')).toBeInTheDocument();
  });
});
