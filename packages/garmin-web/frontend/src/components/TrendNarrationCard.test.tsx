import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "../test/utils";
import TrendNarrationCard from "./TrendNarrationCard";
import type { TrendNarration } from "../api/trends";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * Stub `/api/trends/narration` (latest) and `/api/trends/narration/versions`
 * (all versions, newest first). The versions list defaults to `[latest]`.
 */
function stubNarrationFetch(
  latest: TrendNarration,
  versions: TrendNarration[] = [latest],
): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      if (url.startsWith("/api/trends/narration/versions")) {
        return Promise.resolve(jsonResponse(versions));
      }
      if (url.startsWith("/api/trends/narration")) {
        return Promise.resolve(jsonResponse(latest));
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    }),
  );
}

function makeNarration(
  narrative: string,
  createdAt: string,
): TrendNarration {
  return {
    granularity: "week",
    period_start: "2025-10-06",
    period_end: "2025-10-12",
    analysis_data: { narrative },
    created_at: createdAt,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TrendNarrationCard", () => {
  it("test_renders_narrative_text", async () => {
    const narration = makeNarration(
      "今週は有酸素ベースが順調に積み上がっています。",
      "2025-10-13 10:00:00",
    );
    stubNarrationFetch(narration);

    render(<TrendNarrationCard granularity="week" />);

    expect(
      await screen.findByText(
        "今週は有酸素ベースが順調に積み上がっています。",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "トレンド解説" }),
    ).toBeInTheDocument();
  });

  it("test_version_switcher_swaps_content", async () => {
    // Newest first: v2 is latest, v1 is the older version.
    const v2 = makeNarration("最新版の解説テキストです。", "2025-10-14 10:00:00");
    const v1 = makeNarration("旧版の解説テキストです。", "2025-10-13 10:00:00");
    stubNarrationFetch(v2, [v2, v1]);

    render(<TrendNarrationCard granularity="week" />);

    // Latest version content is shown first.
    expect(
      await screen.findByText("最新版の解説テキストです。"),
    ).toBeInTheDocument();

    const select = await screen.findByLabelText("版を選択:");
    fireEvent.change(select, { target: { value: "1" } });

    // Switching to the older version swaps the displayed prose.
    expect(
      await screen.findByText("旧版の解説テキストです。"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("最新版の解説テキストです。"),
    ).not.toBeInTheDocument();
  });

  it("test_hides_switcher_with_single_version", async () => {
    const narration = makeNarration(
      "単一版の解説テキストです。",
      "2025-10-13 10:00:00",
    );
    stubNarrationFetch(narration, [narration]);

    render(<TrendNarrationCard granularity="week" />);

    expect(
      await screen.findByText("単一版の解説テキストです。"),
    ).toBeInTheDocument();
    // Only one version -> the version switcher is not rendered.
    expect(screen.queryByText("版を選択:")).not.toBeInTheDocument();
  });
});
