import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import QueryBoundary from "./QueryBoundary";

interface Payload {
  x: number;
}

describe("QueryBoundary", () => {
  it("test_query_boundary_shows_skeleton_while_loading", () => {
    render(
      <QueryBoundary<Payload>
        label="走行量"
        query={{ data: undefined, error: null, refetch: vi.fn() }}
      >
        {(data) => <p>x={data.x}</p>}
      </QueryBoundary>,
    );

    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-busy", "true");
    expect(status).toHaveAttribute("aria-label", "走行量");
    // Children never run without data.
    expect(screen.queryByText(/^x=/)).not.toBeInTheDocument();
  });

  it("test_query_boundary_shows_error_with_retry", () => {
    const refetch = vi.fn();
    render(
      <QueryBoundary<Payload>
        label="走行量"
        query={{ data: undefined, error: new Error("boom"), refetch }}
      >
        {(data) => <p>x={data.x}</p>}
      </QueryBoundary>,
    );

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("走行量の読み込みに失敗しました: boom");

    fireEvent.click(screen.getByRole("button", { name: "再試行" }));
    expect(refetch).toHaveBeenCalledTimes(1);
    // The skeleton is not shown alongside the failure.
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("test_query_boundary_renders_children_with_data", () => {
    render(
      <QueryBoundary<Payload>
        label="走行量"
        query={{ data: { x: 1 }, error: null, refetch: vi.fn() }}
      >
        {(data) => <p>x={data.x}</p>}
      </QueryBoundary>,
    );

    expect(screen.getByText("x=1")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
