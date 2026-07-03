import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import EnvironmentReport from "./EnvironmentReport";
import StarRatingBreakdown from "./StarRatingBreakdown";
import SummaryReport from "./SummaryReport";

// Real-schema breakdown emitted by the star-weighting feature (Issue #706).
const envBreakdown = {
  axis_scores: { temperature: 4.3, humidity: 2, terrain: 5, wind: 4 },
  weights: { temperature: 0.4, humidity: 0.3, terrain: 0.2, wind: 0.1 },
  star_rating: 3.8,
};

function section(data: Record<string, unknown>) {
  return { data, parse_error: false, raw: null };
}

describe("StarRatingBreakdown", () => {
  it("test_renders_axis_scores_with_japanese_labels", () => {
    render(<StarRatingBreakdown data={envBreakdown} />);

    // Japanese axis labels, not the raw english keys
    expect(screen.getByText("気温")).toBeInTheDocument();
    expect(screen.getByText("湿度")).toBeInTheDocument();
    expect(screen.getByText("地形")).toBeInTheDocument();
    expect(screen.getByText("風")).toBeInTheDocument();
    expect(screen.queryByText("temperature")).not.toBeInTheDocument();
    expect(screen.queryByText("axis_scores")).not.toBeInTheDocument();

    // Scores rendered to one decimal
    expect(screen.getByText("4.3")).toBeInTheDocument();
    expect(screen.getByText("2.0")).toBeInTheDocument();
    expect(screen.getByText("5.0")).toBeInTheDocument();
  });

  it("test_renders_weights_as_percent", () => {
    render(<StarRatingBreakdown data={envBreakdown} />);

    expect(screen.getByText("40%")).toBeInTheDocument();
    expect(screen.getByText("30%")).toBeInTheDocument();
    expect(screen.getByText("20%")).toBeInTheDocument();
    expect(screen.getByText("10%")).toBeInTheDocument();
  });

  it("test_shows_weighted_total_when_showTotal", () => {
    render(<StarRatingBreakdown data={envBreakdown} />);

    expect(screen.getByText("加重総合")).toBeInTheDocument();
    expect(screen.getByText("3.8 / 5.0")).toBeInTheDocument();
  });

  it("test_hides_total_when_showTotal_false", () => {
    render(<StarRatingBreakdown data={envBreakdown} showTotal={false} />);

    expect(screen.queryByText("加重総合")).not.toBeInTheDocument();
    expect(screen.queryByText("3.8 / 5.0")).not.toBeInTheDocument();
    // Axis rows still render
    expect(screen.getByText("気温")).toBeInTheDocument();
  });

  it("test_unknown_axis_falls_back_to_raw_key", () => {
    render(
      <StarRatingBreakdown
        data={{
          axis_scores: { mystery_axis: 3.5 },
          weights: { mystery_axis: 1.0 },
          star_rating: 3.5,
        }}
      />,
    );

    // Unknown key is shown verbatim rather than crashing
    expect(screen.getByText("mystery_axis")).toBeInTheDocument();
    expect(screen.getByText("3.5")).toBeInTheDocument();
  });

  it("test_returns_null_for_non_object", () => {
    const { container } = render(
      <StarRatingBreakdown data={"3.8" as unknown} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("test_returns_null_without_axis_scores", () => {
    const { container } = render(
      <StarRatingBreakdown data={{ star_rating: 3.8 }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("EnvironmentReport star_rating_breakdown", () => {
  it("test_environment_report_renders_breakdown_not_raw", () => {
    render(
      <EnvironmentReport
        section={section({
          environmental: "気温 18℃ で走りやすいコンディションでした。",
          star_rating_breakdown: envBreakdown,
        })}
      />,
    );

    // Dedicated breakdown UI
    expect(screen.getByText("評価内訳")).toBeInTheDocument();
    expect(screen.getByText("気温")).toBeInTheDocument();
    // Raw english keys must never reach the DOM
    expect(screen.queryByText("star_rating_breakdown")).not.toBeInTheDocument();
    expect(screen.queryByText("axis_scores")).not.toBeInTheDocument();
    expect(screen.queryByText("weights")).not.toBeInTheDocument();
  });
});

describe("SummaryReport star_rating_breakdown", () => {
  it("test_summary_report_hides_duplicate_total", () => {
    render(
      <SummaryReport
        section={section({
          star_rating: "★★★★☆ 3.8/5.0",
          star_rating_breakdown: {
            axis_scores: {
              form_efficiency: 4.0,
              pace_consistency: 3.5,
              hr_management: 4.5,
              execution_quality: 3.0,
            },
            weights: {
              form_efficiency: 0.3,
              pace_consistency: 0.25,
              hr_management: 0.25,
              execution_quality: 0.2,
            },
            star_rating: 3.8,
          },
          summary: "全体として安定したベース走でした。",
        })}
      />,
    );

    // Breakdown axes shown with Japanese labels
    expect(screen.getByText("評価内訳")).toBeInTheDocument();
    expect(screen.getByText("フォーム効率")).toBeInTheDocument();
    expect(screen.getByText("心拍管理")).toBeInTheDocument();
    // No duplicate "加重総合" footer (hero StarRating already shows the total)
    expect(screen.queryByText("加重総合")).not.toBeInTheDocument();
    // Raw english keys must never reach the DOM
    expect(screen.queryByText("star_rating_breakdown")).not.toBeInTheDocument();
    expect(screen.queryByText("axis_scores")).not.toBeInTheDocument();
  });
});
