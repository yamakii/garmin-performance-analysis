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
    return (
      <div className="flex items-center justify-center gap-3 py-16 text-sm text-slate-500">
        <span
          aria-hidden="true"
          className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600"
        />
        読み込み中...
      </div>
    );
  }
  if (error) {
    return (
      <p
        role="alert"
        className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
      >
        エラー: {error}
      </p>
    );
  }
  if (!detail) {
    return (
      <p className="rounded-xl border border-slate-200 bg-white px-4 py-12 text-center text-sm text-slate-500 shadow-sm">
        アクティビティが見つかりません
      </p>
    );
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

  const kpis: { label: string; value: string }[] = [
    { label: "距離", value: formatDistance(activity.total_distance_km) },
    { label: "時間", value: formatDuration(activity.total_time_seconds) },
    { label: "平均ペース", value: formatPace(activity.avg_pace_seconds_per_km) },
    {
      label: "平均心拍",
      value: `${activity.avg_heart_rate ?? "-"} bpm`,
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <Link
          to="/"
          className="text-sm font-medium text-indigo-600 hover:text-indigo-800"
        >
          ← アクティビティ一覧
        </Link>
        <h1 className="mt-2 text-xl font-bold text-slate-900">
          {activity.activity_name ?? "アクティビティ"}{" "}
          <span className="font-normal text-slate-500">
            ({activity.activity_date})
          </span>
        </h1>
      </div>

      {/* KPI header: 4 stat cards */}
      <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {kpis.map(({ label, value }) => (
          <div
            key={label}
            className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
          >
            <dt className="text-xs font-medium tracking-wide text-slate-500 uppercase">
              {label}
            </dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">
              {value}
            </dd>
          </div>
        ))}
      </dl>

      {/* GPS track map (placeholder when the activity has no GPS data) */}
      {track !== null && (
        <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
          <h2 className="px-5 pt-4 pb-2 text-base font-semibold text-slate-800">
            コース
          </h2>
          <div className="overflow-hidden rounded-b-xl">
            <MapPanel
              points={track}
              hoverSeqNo={mapHoverSeqNo}
              onHoverSeqNo={handleMapHover}
            />
          </div>
        </section>
      )}

      {/* Time series chart with metric toggles */}
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="mb-3 text-base font-semibold text-slate-800">
          タイムシリーズ
        </h2>
        <div className="mb-4 flex flex-wrap gap-2">
          {AVAILABLE_METRICS.map(({ key, label }) => {
            const checked = selectedMetrics.includes(key);
            return (
              <label
                key={key}
                className={`inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors ${
                  checked
                    ? "border-indigo-200 bg-indigo-50 text-indigo-700"
                    : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                }`}
              >
                <input
                  type="checkbox"
                  className="accent-indigo-600"
                  checked={checked}
                  onChange={() => toggleMetric(key)}
                />
                {label}
              </label>
            );
          })}
        </div>
        {timeSeries && Object.keys(timeSeries.metrics).length > 0 ? (
          <TimeSeriesChart
            data={timeSeries}
            metricLabels={METRIC_LABELS}
            hoverIndex={chartHoverIndex}
            onHoverIndex={handleChartHover}
          />
        ) : (
          <p className="py-8 text-center text-sm text-slate-500">
            表示する指標を選択してください
          </p>
        )}
      </section>

      {/* Splits table */}
      {splits.length > 0 && (
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 text-base font-semibold text-slate-800">
            スプリット
          </h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs tracking-wide text-slate-500 uppercase">
                <th className="px-2 py-2 text-left font-medium">#</th>
                <th className="px-2 py-2 text-right font-medium">距離</th>
                <th className="px-2 py-2 text-right font-medium">ペース</th>
                <th className="px-2 py-2 text-right font-medium">心拍</th>
                <th className="px-2 py-2 text-right font-medium">ケイデンス</th>
                <th className="px-2 py-2 text-right font-medium">パワー</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {splits.map((split) => (
                <tr key={split.split_index} className="hover:bg-slate-50">
                  <td className="px-2 py-2 text-left tabular-nums text-slate-500">
                    {split.split_index}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">
                    {formatDistance(split.distance)}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">
                    {formatPace(split.pace_seconds_per_km)}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">
                    {split.heart_rate ?? "-"}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">
                    {split.cadence ?? "-"}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">
                    {split.power ?? "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Section analysis cards */}
      {sections && Object.keys(sections).length > 0 && (
        <section>
          <h2 className="mb-3 text-base font-semibold text-slate-800">分析</h2>
          <div className="space-y-4">
            {orderedSectionTypes(sections).map((sectionType) => (
              <SectionCard
                key={sectionType}
                sectionType={sectionType}
                section={sections[sectionType]}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
