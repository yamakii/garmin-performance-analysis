import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  fetchActivityDetail,
  fetchSections,
  fetchTimeSeries,
  fetchTrack,
} from "../api/client";
import MapPanel from "../components/MapPanel";
import SectionCard from "../components/sections/SectionCard";
import TimeSeriesChart from "../components/TimeSeriesChart";
import type {
  ActivityDetailResponse,
  SectionsResponse,
  TimeSeriesResponse,
  TrackPoint,
} from "../types";
import { formatDistance, formatPace } from "./ActivityList";

const AVAILABLE_METRICS: { key: string; label: string }[] = [
  { key: "heart_rate", label: "心拍数" },
  { key: "speed", label: "ペース" },
  { key: "cadence", label: "ケイデンス" },
  { key: "power", label: "パワー" },
  { key: "elevation", label: "高度" },
  { key: "ground_contact_time", label: "接地時間" },
  { key: "vertical_oscillation", label: "上下動" },
  { key: "vertical_ratio", label: "上下動比" },
];

const METRIC_LABELS: Record<string, string> = Object.fromEntries(
  AVAILABLE_METRICS.map(({ key, label }) => [key, label]),
);

const DEFAULT_METRICS = ["heart_rate", "speed"];

const SECTION_ORDER = ["summary", "split", "phase", "efficiency", "environment"];

export function formatDuration(totalSeconds: number | null): string {
  if (totalSeconds == null || totalSeconds < 0) {
    return "-";
  }
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = Math.floor(totalSeconds % 60);
  const mmss = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  return hours > 0 ? `${hours}:${mmss}` : mmss;
}

/** Binary search: index of the timestamp nearest to target (ascending). */
export function nearestTimestampIndex(
  timestamps: number[],
  target: number,
): number {
  let low = 0;
  let high = timestamps.length - 1;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (timestamps[mid] < target) {
      low = mid + 1;
    } else {
      high = mid;
    }
  }
  if (low > 0 && target - timestamps[low - 1] <= timestamps[low] - target) {
    return low - 1;
  }
  return low;
}

/** Shared hover state in the seq_no / timestamp_s domain. */
interface HoverState {
  source: "chart" | "map";
  value: number;
}

function orderedSectionTypes(sections: SectionsResponse): string[] {
  const known = SECTION_ORDER.filter((type) => type in sections);
  const unknown = Object.keys(sections).filter(
    (type) => !SECTION_ORDER.includes(type),
  );
  return [...known, ...unknown];
}

export default function ActivityDetail() {
  const { id } = useParams<{ id: string }>();
  const [detail, setDetail] = useState<ActivityDetailResponse | null>(null);
  const [sections, setSections] = useState<SectionsResponse | null>(null);
  const [timeSeries, setTimeSeries] = useState<TimeSeriesResponse | null>(null);
  const [selectedMetrics, setSelectedMetrics] =
    useState<string[]>(DEFAULT_METRICS);
  const [track, setTrack] = useState<TrackPoint[] | null>(null);
  const [hover, setHover] = useState<HoverState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    Promise.all([fetchActivityDetail(id), fetchSections(id)])
      .then(([detailData, sectionsData]) => {
        if (!cancelled) {
          setDetail(detailData);
          setSections(sectionsData);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  useEffect(() => {
    if (!id || selectedMetrics.length === 0) {
      setTimeSeries(null);
      return;
    }
    let cancelled = false;
    fetchTimeSeries(id, selectedMetrics)
      .then((data) => {
        if (!cancelled) {
          setTimeSeries(data);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setTimeSeries(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [id, selectedMetrics]);

  useEffect(() => {
    if (!id) {
      return;
    }
    let cancelled = false;
    fetchTrack(id)
      .then((data) => {
        if (!cancelled) {
          setTrack(data.points);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setTrack([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const toggleMetric = (key: string) => {
    setSelectedMetrics((current) =>
      current.includes(key)
        ? current.filter((metric) => metric !== key)
        : [
            ...AVAILABLE_METRICS.map((metric) => metric.key).filter(
              (metric) => current.includes(metric) || metric === key,
            ),
          ],
    );
  };

  if (loading) {
    return <p>読み込み中...</p>;
  }
  if (error) {
    return <p role="alert">エラー: {error}</p>;
  }
  if (!detail) {
    return <p>アクティビティが見つかりません</p>;
  }

  const { activity, splits } = detail;

  // Bidirectional hover sync: chart data index <-> track seq_no, matched
  // through the nearest timestamp / seq_no value.
  const timestamps = timeSeries?.timestamps ?? [];
  const chartHoverIndex =
    hover?.source === "map" && timestamps.length > 0
      ? nearestTimestampIndex(timestamps, hover.value)
      : null;
  const mapHoverSeqNo = hover?.value ?? null;

  const handleChartHover = (index: number | null) => {
    setHover(
      index == null || timestamps.length === 0
        ? null
        : { source: "chart", value: timestamps[index] ?? index },
    );
  };

  const handleMapHover = (seqNo: number | null) => {
    setHover(seqNo == null ? null : { source: "map", value: seqNo });
  };

  return (
    <div>
      <p>
        <Link to="/">← アクティビティ一覧</Link>
      </p>
      <h1>
        {activity.activity_name ?? "アクティビティ"} ({activity.activity_date})
      </h1>

      {/* KPI header */}
      <dl className="kpi-header">
        <div>
          <dt>距離</dt>
          <dd>{formatDistance(activity.total_distance_km)}</dd>
        </div>
        <div>
          <dt>時間</dt>
          <dd>{formatDuration(activity.total_time_seconds)}</dd>
        </div>
        <div>
          <dt>平均ペース</dt>
          <dd>{formatPace(activity.avg_pace_seconds_per_km)}</dd>
        </div>
        <div>
          <dt>平均心拍</dt>
          <dd>{activity.avg_heart_rate ?? "-"} bpm</dd>
        </div>
      </dl>

      {/* GPS track map (placeholder when the activity has no GPS data) */}
      {track !== null && (
        <section>
          <h2>コース</h2>
          <MapPanel
            points={track}
            hoverSeqNo={mapHoverSeqNo}
            onHoverSeqNo={handleMapHover}
          />
        </section>
      )}

      {/* Time series chart with metric toggles */}
      <section>
        <h2>タイムシリーズ</h2>
        <div className="metric-toggles">
          {AVAILABLE_METRICS.map(({ key, label }) => (
            <label key={key} style={{ marginRight: "1em" }}>
              <input
                type="checkbox"
                checked={selectedMetrics.includes(key)}
                onChange={() => toggleMetric(key)}
              />
              {label}
            </label>
          ))}
        </div>
        {timeSeries && Object.keys(timeSeries.metrics).length > 0 ? (
          <TimeSeriesChart
            data={timeSeries}
            metricLabels={METRIC_LABELS}
            hoverIndex={chartHoverIndex}
            onHoverIndex={handleChartHover}
          />
        ) : (
          <p>表示する指標を選択してください</p>
        )}
      </section>

      {/* Splits table */}
      {splits.length > 0 && (
        <section>
          <h2>スプリット</h2>
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>距離</th>
                <th>ペース</th>
                <th>心拍</th>
                <th>ケイデンス</th>
                <th>パワー</th>
              </tr>
            </thead>
            <tbody>
              {splits.map((split) => (
                <tr key={split.split_index}>
                  <td>{split.split_index}</td>
                  <td>{formatDistance(split.distance)}</td>
                  <td>{formatPace(split.pace_seconds_per_km)}</td>
                  <td>{split.heart_rate ?? "-"}</td>
                  <td>{split.cadence ?? "-"}</td>
                  <td>{split.power ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Section analysis cards */}
      {sections && Object.keys(sections).length > 0 && (
        <section>
          <h2>分析</h2>
          {orderedSectionTypes(sections).map((sectionType) => (
            <SectionCard
              key={sectionType}
              sectionType={sectionType}
              section={sections[sectionType]}
            />
          ))}
        </section>
      )}
    </div>
  );
}
