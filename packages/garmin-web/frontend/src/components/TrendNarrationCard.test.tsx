import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "../test/utils";
import TrendNarrationCard, { narrationLead } from "./TrendNarrationCard";
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
    // The prose lives behind the disclosure, not under a heading of its own:
    // the page's only h1 is its verdict and the metric blocks own the h2s.
    expect(
      screen.getByText("コーチ解説の全文"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading")).toBeNull();
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

  it("test_narration_full_text_behind_disclosure", async () => {
    // A long write-up is carried in full behind the disclosure — it is the
    // "全文", so nothing in it is clamped away; the version switcher sits
    // inside the same fold.
    const longNarrative = Array.from(
      { length: 12 },
      (_, i) => `${i + 1}段落目の詳細な解説テキストです。`,
    ).join("\n");
    const v2 = makeNarration(longNarrative, "2025-10-14 10:00:00");
    const v1 = makeNarration("旧版の解説テキストです。", "2025-10-13 10:00:00");
    stubNarrationFetch(v2, [v2, v1]);

    render(<TrendNarrationCard granularity="week" />);

    expect(await screen.findByText("コーチ解説の全文")).toBeInTheDocument();
    expect(await screen.findByLabelText("版を選択:")).toBeInTheDocument();
    expect(
      screen.getByText(/12段落目の詳細な解説テキストです。/),
    ).toBeInTheDocument();
    // The old 続きを読む clamp is gone: the fold is the progressive disclosure.
    expect(screen.queryByRole("button", { name: "続きを読む" })).toBeNull();
  });

  it("test_narration_lead_first_paragraph", () => {
    expect(
      narrationLead(makeNarration("一段落目。\n\n二段落目", "2025-10-14")),
    ).toBe("一段落目。");
    // Nothing quotable in the payload -> an empty lead, not "undefined".
    expect(
      narrationLead({
        granularity: "week",
        period_start: "2025-10-06",
        period_end: "2025-10-12",
        analysis_data: { points: ["箇条書きは見出しにしない"] },
        created_at: null,
      }),
    ).toBe("");
  });

  it("test_narration_card_renders_nothing_while_pending", () => {
    // A fetch that never settles keeps the narration query pending.
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );

    const { container } = render(<TrendNarrationCard granularity="week" />);

    // This card is only a disclosure now — the lead moved to the page — so a
    // placeholder for it would sit between the verdict line and the vitals
    // row while loading, splitting the two things the page is read for
    // (#1193). It renders nothing instead.
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
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
