import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { FormAnomalyFlag, FormAnomalyFlagsResponse } from "../../types";
import FormAnomalyFlagsCard from "./FormAnomalyFlagsCard";

function buildResponse(
  flags: FormAnomalyFlag[],
): FormAnomalyFlagsResponse {
  return { weeks: 4, scanned: 8, limited: false, flags };
}

describe("FormAnomalyFlagsCard", () => {
  it("FormAnomalyFlagsCard shows 問題なし badge when no flags", () => {
    render(<FormAnomalyFlagsCard data={buildResponse([])} />);

    const badge = screen.getByText("問題なし");
    expect(badge).toHaveClass("bg-status-good/10");
    expect(badge).toHaveClass("text-status-good");
  });

  it("FormAnomalyFlagsCard shows count badge when flags exist", () => {
    const flags: FormAnomalyFlag[] = [
      {
        activity_id: 1,
        activity_date: "2025-10-01",
        anomalies_detected: 2,
        severity_high: 1,
        top_recommendation: "ピッチを上げる",
      },
      {
        activity_id: 2,
        activity_date: "2025-10-03",
        anomalies_detected: 1,
        severity_high: 0,
        top_recommendation: null,
      },
    ];
    render(<FormAnomalyFlagsCard data={buildResponse(flags)} />);

    const badge = screen.getByText("2件");
    expect(badge).toHaveClass("bg-status-warn/10");
    expect(badge).toHaveClass("text-status-warn");
  });
});
