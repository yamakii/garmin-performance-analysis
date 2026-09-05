import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "../test/utils";
import { makeMonthPlan } from "../test/planFixture";
import Plan from "./Plan";

function stubFetch(): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    const month = /month=(\d{4}-\d{2})/.exec(url)?.[1] ?? "2026-09";
    return Promise.resolve(
      new Response(JSON.stringify(makeMonthPlan(month)), {
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
      screen.getByRole("heading", { level: 1, name: "計画" }),
    ).toBeInTheDocument();
    expect(screen.getByText("2026年9月")).toBeInTheDocument();
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

    // The block the month sits inside, and the month's own adherence.
    expect(screen.getByText("新潟マラソン ビルド")).toBeInTheDocument();
    expect(screen.getByText("4/6 実施")).toBeInTheDocument();
  });

  it("test_plan_month_navigation_updates_url", async () => {
    const fetchMock = stubFetch();
    renderPlan();

    expect(await screen.findByText("2026年9月")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "前の月" }));

    expect(await screen.findByText("2026年8月")).toBeInTheDocument();
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/plan/month?month=2026-08");
    });
  });

  it("falls back to the current month when the URL month is malformed", async () => {
    const fetchMock = stubFetch();
    renderPlan("/plan?month=2026-9");

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });
    const requested = String(fetchMock.mock.calls[0][0]);
    expect(requested).not.toContain("2026-9&");
    expect(requested).toMatch(/^\/api\/plan\/month\?month=\d{4}-\d{2}$/);
  });
});
