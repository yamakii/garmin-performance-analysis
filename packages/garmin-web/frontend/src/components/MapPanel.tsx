import type { LatLngBoundsExpression, LeafletMouseEvent } from "leaflet";
import { useMemo, useRef } from "react";
import { CircleMarker, MapContainer, Polyline, TileLayer } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type { TrackPoint } from "../types";
import { INK_COLOR } from "./chartTheme";

const HOVER_THROTTLE_MS = 50;

/** Gold (#214 --color-gold): the hover marker echoes the star-rating accent. */
const HOVER_MARKER_COLOR = "#f59e0b";

/** Binary search: index of the point whose seq_no is nearest to target. */
export function nearestPointIndex(points: TrackPoint[], target: number): number {
  let low = 0;
  let high = points.length - 1;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (points[mid].seq_no < target) {
      low = mid + 1;
    } else {
      high = mid;
    }
  }
  if (low > 0) {
    const prev = points[low - 1];
    if (target - prev.seq_no <= points[low].seq_no - target) {
      return low - 1;
    }
  }
  return low;
}

function nearestPointToLatLng(
  points: TrackPoint[],
  lat: number,
  lng: number,
): TrackPoint {
  let best = points[0];
  let bestDist = Infinity;
  for (const point of points) {
    const dLat = point.lat - lat;
    const dLon = point.lon - lng;
    const dist = dLat * dLat + dLon * dLon;
    if (dist < bestDist) {
      bestDist = dist;
      best = point;
    }
  }
  return best;
}

/**
 * GPS track map (Leaflet + OpenStreetMap). Renders a placeholder when the
 * activity has no GPS points (e.g. indoor runs). Hovering the polyline
 * reports the nearest point's seq_no via onHoverSeqNo (throttled 50ms);
 * hoverSeqNo highlights the nearest point with a marker.
 */
export default function MapPanel({
  points,
  hoverSeqNo,
  onHoverSeqNo,
}: {
  points: TrackPoint[];
  hoverSeqNo?: number | null;
  onHoverSeqNo?: (seqNo: number | null) => void;
}) {
  const lastEmitRef = useRef(0);

  const positions = useMemo(
    () => points.map((point) => [point.lat, point.lon] as [number, number]),
    [points],
  );

  const bounds = useMemo<LatLngBoundsExpression | null>(() => {
    if (points.length === 0) {
      return null;
    }
    const lats = points.map((point) => point.lat);
    const lons = points.map((point) => point.lon);
    return [
      [Math.min(...lats), Math.min(...lons)],
      [Math.max(...lats), Math.max(...lons)],
    ];
  }, [points]);

  if (points.length === 0 || bounds == null) {
    return (
      <p className="px-5 py-8 text-center text-sm text-slate-500">
        GPSデータがありません
      </p>
    );
  }

  const hoverPoint =
    hoverSeqNo == null ? null : points[nearestPointIndex(points, hoverSeqNo)];

  const handleMouseMove = (event: LeafletMouseEvent) => {
    if (!onHoverSeqNo) {
      return;
    }
    const now = Date.now();
    if (now - lastEmitRef.current < HOVER_THROTTLE_MS) {
      return;
    }
    lastEmitRef.current = now;
    const nearest = nearestPointToLatLng(
      points,
      event.latlng.lat,
      event.latlng.lng,
    );
    onHoverSeqNo(nearest.seq_no);
  };

  return (
    <MapContainer
      bounds={bounds}
      scrollWheelZoom={false}
      style={{ width: "100%", height: 400 }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Polyline
        positions={positions}
        pathOptions={{ color: INK_COLOR, weight: 4 }}
        eventHandlers={{
          mousemove: handleMouseMove,
          mouseout: () => onHoverSeqNo?.(null),
        }}
      />
      {hoverPoint && (
        <CircleMarker
          center={[hoverPoint.lat, hoverPoint.lon]}
          radius={7}
          pathOptions={{
            color: HOVER_MARKER_COLOR,
            fillColor: HOVER_MARKER_COLOR,
            fillOpacity: 0.9,
          }}
        />
      )}
    </MapContainer>
  );
}
