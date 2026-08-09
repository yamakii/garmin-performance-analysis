import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RecoveryStatus, WellnessBaselineDeviation } from "../../types";
import TodayHero, { verdictMeta } from "./TodayHero";

function makeStatus(overrides: Partial<RecoveryStatus> = {}): RecoveryStatus {
  return {
    date: "2026-07-02",
    recommendation: "easy",
    score: 59,
    reasons: ["HRVが2夜連続でベースラインを下回っています"],
    training_readiness: 59,
    body_battery_high: 80,
    sleep_score: 61,
    ...overrides,
  };
}

function makeBaseline(
  overrides: Partial<WellnessBaselineDeviation> = {},
): WellnessBaselineDeviation {
  const within = {
    mean: 60,
    std: 5,
    n: 30,
    flag: "within" as const,
    adverse: false,
  };
  return {
    date: "2026-07-02",
    hrv: { metric: "hrv", today: 51, z: -1.69, ...within },
    readiness: { metric: "readiness", today: 59, z: -0.5, ...within },
    rhr: { metric: "rhr", today: 48, z: 1.24, ...within },
    overall_flag: false,
    ...overrides,
  };
}

describe("verdictMeta", () => {
  it("maps each recommendation to its verdict label and tone", () => {
    expect(verdictMeta("quality")).toMatchObject({
      label: "質練OK",
      tone: "good",
    });
    expect(verdictMeta("moderate")).toMatchObject({ tone: "info" });
    expect(verdictMeta("easy")).toMatchObject({
      label: "イージー推奨",
      tone: "warn",
    });
    expect(verdictMeta("rest")).toMatchObject({
      label: "休養推奨",
      tone: "bad",
    });
    expect(verdictMeta("unknown")).toMatchObject({
      label: "データなし",
      tone: "neutral",
    });
  });
});

describe("TodayHero", () => {
  it("test_today_hero_verdict_is_heading", () => {
    render(<TodayHero status={makeStatus()} baseline={makeBaseline()} />);

    // The one thing the hero exists to say belongs in the page outline, not in
    // an anonymous paragraph (#912).
    expect(
      screen.getByRole("heading", { level: 2, name: "イージー推奨" }),
    ).toBeInTheDocument();
    // The English eyebrow only restates it, so it stays out of the outline.
    expect(
      screen.queryByRole("heading", { name: /Today/ }),
    ).not.toBeInTheDocument();
  });

  it("renders the verdict, leading rationale and wellness chips", () => {
    render(<TodayHero status={makeStatus()} baseline={makeBaseline()} />);

    expect(screen.getByText("イージー推奨")).toBeInTheDocument();
    expect(
      screen.getByText("HRVが2夜連続でベースラインを下回っています"),
    ).toBeInTheDocument();
    expect(screen.getByText("準備度")).toBeInTheDocument();
    expect(screen.getByText("51ms")).toBeInTheDocument();
    expect(screen.getByText("48bpm")).toBeInTheDocument();
    // No baseline alert when overall_flag is false.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("falls back to the gloss when no reason is provided", () => {
    render(
      <TodayHero
        status={makeStatus({ recommendation: "unknown", reasons: [] })}
        baseline={null}
      />,
    );

    expect(screen.getByText("データなし")).toBeInTheDocument();
    expect(
      screen.getByText("感覚を優先して判断してください"),
    ).toBeInTheDocument();
  });

  it("flags adverse baseline metrics and shows the overall alert", () => {
    const baseline = makeBaseline({ overall_flag: true });
    baseline.hrv = { ...baseline.hrv, flag: "low", adverse: true };

    render(<TodayHero status={makeStatus()} baseline={baseline} />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "個人ベースラインから不利な方向に逸脱中",
    );
    expect(screen.getByText("基準外")).toBeInTheDocument();
  });
});
