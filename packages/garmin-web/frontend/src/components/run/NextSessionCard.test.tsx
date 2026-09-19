import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import NextSessionCard from "./NextSessionCard";
import type { NextSession } from "../../types";

const SESSION: NextSession = {
  date: "2026-09-20",
  days_ahead: 2,
  session_type: "long",
  session_label_ja: "ロング走",
  title: "ロング 16km",
  target_km: 16,
  target_minutes: null,
  hr_low: null,
  hr_high: 150,
  source: "prescription",
};

describe("NextSessionCard", () => {
  it("states when the session is, what it is and its ceiling", () => {
    render(<NextSessionCard session={SESSION} />);

    expect(screen.getByText("9/20（2日後）")).toBeInTheDocument();
    expect(screen.getByText("ロング走")).toBeInTheDocument();
    expect(screen.getByText("16 km")).toBeInTheDocument();
    expect(screen.getByText("150 bpm 以下")).toBeInTheDocument();
  });

  it("falls back to minutes and omits what the plan does not say", () => {
    render(
      <NextSessionCard
        session={{
          ...SESSION,
          session_label_ja: "リカバリー",
          target_km: null,
          target_minutes: 30,
          hr_high: null,
        }}
      />,
    );

    // A time-based session is stated in minutes; an absent ceiling is simply
    // not shown rather than rendered as a bare unit.
    expect(screen.getByText("30 分")).toBeInTheDocument();
    expect(screen.queryByText(/bpm/)).not.toBeInTheDocument();
  });

  it("drops the date line for a dateless session", () => {
    render(
      <NextSessionCard
        session={{ ...SESSION, date: null, days_ahead: null }}
      />,
    );

    expect(screen.queryByText("予定")).not.toBeInTheDocument();
    expect(screen.getByText("ロング走")).toBeInTheDocument();
  });
});
