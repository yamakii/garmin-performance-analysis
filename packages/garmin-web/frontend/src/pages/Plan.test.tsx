import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "../test/utils";
import { makeMonthPlan } from "../test/planFixture";
import Plan from "./Plan";

const REVIEW = {
  review_id: 42,
  user_id: "default",
  week_start_date: "2026-09-07",
  week_end_date: "2026-09-13",
  review_date: "2026-09-14",
  review_data: {
    recommendations: ["今週はロングを22kmに伸ばし、心拍150以下で通しましょう。"],
  },
  created_at: "2026-09-14T09:00:00",
  agent_name: "weekly-review",
  agent_version: "1",
};

function stubFetch(): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    const body = url.includes("/api/weekly-reviews")
      ? [REVIEW]
      : makeMonthPlan(/month=(\d{4}-\d{2})/.exec(url)?.[1] ?? "2026-09");
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderPlan(path = "/plan?month=2026-09") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Plan />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Plan", () => {
  it("test_plan_renders_month_grid", async () => {
    stubFetch();
    renderPlan();

    expect(
      screen.getByRole("heading", { level: 1, name: "2026年9月" }),
    ).toBeInTheDocument();
    // The grid arrives with the month payload.
    expect(
      await screen.findByRole("table", { name: "月間プラン" }),
    ).toBeInTheDocument();

    // Five week rows for September 2026 (2026-08-31 .. 2026-10-04).
    const [, body] = screen.getAllByRole("rowgroup");
    expect(within(body).getAllByRole("row")).toHaveLength(5);

    // Each row leads to that week's review.
    expect(screen.getByRole("link", { name: "9/7週" })).toHaveAttribute(
      "href",
      "/weekly-reviews/2026-09-07",
    );

    // The block the month sits inside is drawn as a band over the grid.
    expect(screen.getByText(/新潟マラソン ビルド/)).toBeInTheDocument();
    // The month in four numbers: 75km prescribed, 21.4km run, 4 of 5 settled.
    expect(screen.getByText("75km")).toBeInTheDocument();
    expect(screen.getByText("21.4km")).toBeInTheDocument();
    expect(screen.getByText("4/5")).toBeInTheDocument();
    expect(screen.getByText("週2")).toBeInTheDocument();
    expect(screen.getByText(/今月の処方 6 本のうち 4 本実施/)).toBeInTheDocument();
  });

  it("test_plan_month_nav_buttons", async () => {
    const fetchMock = stubFetch();
    renderPlan();

    expect(await screen.findByText("2026年9月")).toBeInTheDocument();
    const previous = screen.getByRole("button", { name: "前の月" });
    expect(previous.textContent).toBe("← 8月");
    expect(screen.getByRole("button", { name: "次の月" }).textContent).toBe(
      "10月 →",
    );

    fireEvent.click(previous);
    expect(await screen.findByText("2026年8月")).toBeInTheDocument();
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/plan/month?month=2026-08");
    });

    fireEvent.click(screen.getByRole("button", { name: "次の月" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/plan/month?month=2026-09");
    });
  });

  it("test_plan_legend_and_coach_note", async () => {
    stubFetch();
    renderPlan();

    // The legend explains what the grid's states look like.
    expect(await screen.findByText(/太字 \+ 実績行/)).toBeInTheDocument();

    // The last word on the page is the coach's, quoted from the latest review.
    const note = await screen.findByText(
      /今週はロングを22kmに伸ばし/,
      {},
      { timeout: 2000 },
    );
    expect(note).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "レビュー全文 →" })).toHaveAttribute(
      "href",
      "/weekly-reviews/2026-09-07",
    );
  });

  it("test_plan_bands_inside_month_grid_scroller", async () => {
    stubFetch();
    renderPlan();

    // The band and the days it labels scroll together: a band drawn outside
    // the grid's scroller keeps its place while the days move under it, so a
    // phase change lands on the wrong day (#1143).
    const band = await screen.findByText(/新潟マラソン ビルド/);
    const scroller = band.closest(".overflow-x-auto");
    expect(scroller).not.toBeNull();
    expect(scroller).toContainElement(
      screen.getByRole("table", { name: "月間プラン" }),
    );
  });

  it("falls back to the current month when the URL month is malformed", async () => {
    const fetchMock = stubFetch();
    renderPlan("/plan?month=2026-9");

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });
    const requested = fetchMock.mock.calls
      .map((call) => String(call[0]))
      .find((url) => url.startsWith("/api/plan/month"));
    expect(requested).not.toContain("2026-9&");
    expect(requested).toMatch(/^\/api\/plan\/month\?month=\d{4}-\d{2}$/);
  });
});
