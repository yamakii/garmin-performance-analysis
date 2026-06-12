import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { TrackPoint } from "../types";
import MapPanel, { nearestPointIndex } from "./MapPanel";

// Leaflet needs a real DOM/canvas, which jsdom does not provide.
vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="map-container">{children}</div>
  ),
  TileLayer: () => <div data-testid="tile-layer" />,
  Polyline: () => <div data-testid="polyline" />,
  CircleMarker: () => <div data-testid="hover-marker" />,
}));
vi.mock("leaflet/dist/leaflet.css", () => ({}));

const POINTS: TrackPoint[] = [
  { seq_no: 0, lat: 35.6, lon: 139.7 },
  { seq_no: 5, lat: 35.601, lon: 139.701 },
  { seq_no: 10, lat: 35.602, lon: 139.702 },
];

describe("MapPanel", () => {
  it("MapPanel renders nothing when points empty", () => {
    render(<MapPanel points={[]} />);

    expect(screen.getByText("GPSデータがありません")).toBeInTheDocument();
    expect(screen.queryByTestId("map-container")).not.toBeInTheDocument();
  });

  it("renders map with polyline when points exist", () => {
    render(<MapPanel points={POINTS} />);

    expect(screen.getByTestId("map-container")).toBeInTheDocument();
    expect(screen.getByTestId("polyline")).toBeInTheDocument();
    expect(screen.queryByText("GPSデータがありません")).not.toBeInTheDocument();
  });

  it("shows hover marker for the nearest seq_no", () => {
    render(<MapPanel points={POINTS} hoverSeqNo={6} />);

    expect(screen.getByTestId("hover-marker")).toBeInTheDocument();
  });

  it("nearestPointIndex picks the closest seq_no", () => {
    expect(nearestPointIndex(POINTS, 0)).toBe(0);
    expect(nearestPointIndex(POINTS, 2)).toBe(0);
    expect(nearestPointIndex(POINTS, 3)).toBe(1);
    expect(nearestPointIndex(POINTS, 6)).toBe(1);
    expect(nearestPointIndex(POINTS, 9)).toBe(2);
    expect(nearestPointIndex(POINTS, 999)).toBe(2);
  });
});
