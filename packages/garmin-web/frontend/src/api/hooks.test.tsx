import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useActivityDetail } from "./hooks";

/** A fresh, retry-free QueryClient wrapper so each test starts with an empty cache. */
function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
  };
}

const DETAIL = {
  activity: {
    activity_id: 123,
    activity_date: "2025-10-09",
    activity_name: "Morning Run",
    total_distance_km: 5.66,
    total_time_seconds: 2186,
    avg_pace_seconds_per_km: 386,
    avg_heart_rate: 144,
  },
  splits: [],
  form_efficiency: null,
  hr_zones: [],
  performance_trends: null,
  form_evaluations: null,
  vo2_max: null,
  lactate_threshold: null,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function detailCalls(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter(([input]) =>
    String(input).includes("/api/activities/123"),
  ).length;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useActivityDetail", () => {
  it("同一キーの2回マウントで fetch は1回", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(DETAIL));
    vi.stubGlobal("fetch", fetchMock);

    // Two components read the same [activity, 123] key from one shared client:
    // react-query dedupes them into a single in-flight request.
    const { result } = renderHook(
      () => ({
        a: useActivityDetail("123"),
        b: useActivityDetail("123"),
      }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => {
      expect(result.current.a.isSuccess).toBe(true);
      expect(result.current.b.isSuccess).toBe(true);
    });

    expect(detailCalls(fetchMock)).toBe(1);
  });

  it("エラー時に error が返り refetch で回復する", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "boom" }, 500))
      .mockResolvedValue(jsonResponse(DETAIL));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useActivityDetail("123"), {
      wrapper: createWrapper(),
    });

    // First attempt fails (retry disabled), so the error surfaces immediately.
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).not.toBeNull();

    // Retrying re-runs the query; the second attempt succeeds.
    await result.current.refetch();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(DETAIL);
    expect(detailCalls(fetchMock)).toBe(2);
  });
});
