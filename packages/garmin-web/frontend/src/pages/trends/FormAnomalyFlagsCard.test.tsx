import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { FormAnomalyFlag, FormAnomalyFlagsResponse } from "../../types";
import FormAnomalyFlagsCard from "./FormAnomalyFlagsCard";

function buildResponse(flags: FormAnomalyFlag[]): FormAnomalyFlagsResponse {
  return { weeks: 4, scanned: 8, limited: false, flags };
}

function renderCard(data: FormAnomalyFlagsResponse) {
  return render(
    <MemoryRouter>
      <FormAnomalyFlagsCard data={data} />
    </MemoryRouter>,
  );
}

describe("FormAnomalyFlagsCard", () => {
  it("test_form_anomaly_block_links_activity", () => {
    const flags: FormAnomalyFlag[] = [
      {
        activity_id: 1,
        activity_date: "2025-10-01",
        anomalies_detected: 2,
        severity_high: 1,
        top_recommendation: "ピッチを上げる",
      },
    ];
    renderCard(buildResponse(flags));

    // The next question after "何かあった?" is "どの走りで?".
    const link = screen.getByRole("link", { name: "ランを見る →" });
    expect(link).toHaveAttribute("href", "/activities/1");
    expect(link.closest("li")).toHaveClass("bg-warn-tint");

    expect(screen.getByText(/異常 2件（高 1）/)).toBeInTheDocument();
    expect(screen.getByText("ピッチを上げる")).toBeInTheDocument();
  });

  it("states the quiet morning as one muted sentence", () => {
    renderCard(buildResponse([]));

    expect(
      screen.getByText("直近のランでフォームの異常は検出されていません。"),
    ).toHaveClass("text-ink-muted");
    // No badge, no tint: an empty list is the normal case.
    expect(screen.queryByText("問題なし")).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
  });
});
