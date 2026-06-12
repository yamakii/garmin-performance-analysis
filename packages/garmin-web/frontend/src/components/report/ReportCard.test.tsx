import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import FallbackFields from "./FallbackFields";
import ReportCard from "./ReportCard";

describe("ReportCard", () => {
  it("shows raw text when JSON parsing failed", () => {
    const section = {
      data: null,
      parse_error: true,
      raw: '{"metadata": broken',
    };

    render(
      <ReportCard title="環境影響" section={section}>
        {(data) => <FallbackFields data={data} />}
      </ReportCard>,
    );

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText('{"metadata": broken')).toBeInTheDocument();
  });

  it("renders nothing when the section is missing", () => {
    const { container } = render(
      <ReportCard title="総合評価" section={undefined}>
        {(data) => <FallbackFields data={data} />}
      </ReportCard>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders unknown structure without crashing via fallback", () => {
    const section = {
      data: { metadata: { activity_id: "99999999" }, test: "テストデータ" },
      parse_error: false,
      raw: null,
    };

    render(
      <ReportCard title="mystery" section={section}>
        {(data) => <FallbackFields data={data} exclude={["metadata"]} />}
      </ReportCard>,
    );

    expect(screen.getByText("test")).toBeInTheDocument();
    expect(screen.getByText("テストデータ")).toBeInTheDocument();
    expect(screen.queryByText("metadata")).not.toBeInTheDocument();
  });
});
