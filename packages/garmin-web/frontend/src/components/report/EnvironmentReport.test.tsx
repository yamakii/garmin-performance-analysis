import { describe, expect, it } from "vitest";
import { render, screen } from "../../test/utils";
import EnvironmentReport from "./EnvironmentReport";

const breakdown = {
  axis_scores: { temperature: 4.3, humidity: 2, terrain: 5, wind: 4 },
  weights: { temperature: 0.4, humidity: 0.3, terrain: 0.2, wind: 0.1 },
  star_rating: 3.8,
};

const PROSE = [
  "気温18度・湿度62%は有酸素走にとって走りやすい条件でした。",
  "風速2m/sの向かい風は2km地点から3km地点にかけて体感されています。",
  "地形は累積標高32mでほぼフラットに近く、ペースへの影響は限定的でした。",
  "路面はドライで、接地が乱れる要因は見当たりません。",
  "日射は雲に遮られ、体温上昇のリスクは小さい状況でした。",
  "総合すると環境が走りを妨げた場面はほとんどありません。",
].join("");

function section(data: Record<string, unknown>) {
  return { data, parse_error: false, raw: null };
}

describe("EnvironmentReport", () => {
  it("test_environment_clamped_with_breakdown_first", () => {
    render(
      <EnvironmentReport
        section={section({
          environmental: `${PROSE}(★★★★☆ 3.8/5.0)`,
          star_rating_breakdown: breakdown,
        })}
      />,
    );

    // The weighted axis bars lead; the prose follows them in the DOM.
    const bars = screen.getByText("評価内訳");
    const prose = screen.getByText(PROSE);
    expect(
      bars.compareDocumentPosition(prose) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    // The prose is clamped with a reveal toggle instead of running long.
    expect(
      screen.getByRole("button", { name: "続きを読む" }),
    ).toBeInTheDocument();

    // The trailing rating becomes a heading badge.
    expect(screen.getByText("★ 3.8")).toBeInTheDocument();
    expect(screen.queryByText(/3\.8\/5\.0/)).not.toBeInTheDocument();
  });

  it("test_environment_without_breakdown_still_renders_prose", () => {
    render(<EnvironmentReport section={section({ environmental: PROSE })} />);

    expect(screen.getByText(PROSE)).toBeInTheDocument();
    // No breakdown payload -> no bars, and no badge without a star suffix.
    expect(screen.queryByText("評価内訳")).not.toBeInTheDocument();
    expect(screen.queryByText(/^★ /)).not.toBeInTheDocument();
  });
});
