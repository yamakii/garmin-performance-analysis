import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  fetchActivityDetail,
  fetchSections,
  fetchTimeSeries,
  fetchTrack,
} from "../api/client";
import { METRIC_COLORS } from "../components/chartTheme";
import HeroHeader from "../components/HeroHeader";
import MapPanel from "../components/MapPanel";
import EfficiencyReport from "../components/report/EfficiencyReport";
import EnvironmentReport from "../components/report/EnvironmentReport";
import FallbackFields from "../components/report/FallbackFields";
import PhaseTimeline from "../components/report/PhaseTimeline";
import ReportCard, { isRecord } from "../components/report/ReportCard";
import SplitNarrative from "../components/report/SplitNarrative";
import SummaryReport from "../components/report/SummaryReport";
import TimeSeriesChart from "../components/TimeSeriesChart";
import type {
  ActivityDetailResponse,
  SectionsResponse,
  TimeSeriesResponse,
  TrackPoint,
} from "../types";
import { formatCadence, formatDistance, formatPace } from "./ActivityList";

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

// Section types with dedicated report components; others fall back.
const KNOWN_SECTION_TYPES = [
  "summary",
  "split",
  "phase",
  "efficiency",
  "environment",
];

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

function summaryStarRating(sections: SectionsResponse | null): string | null {
  const data = sections?.summary?.data;
  if (isRecord(data) && typeof data.star_rating === "string") {
    return data.star_rating;
  }
  return null;
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
          className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-ink"
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

  const { splits } = detail;

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

  const starRating = summaryStarRating(sections);
  const unknownSectionTypes = sections
    ? Object.keys(sections).filter(
        (type) => !KNOWN_SECTION_TYPES.includes(type),
      )
    : [];

  return (
    <div className="stagger-in space-y-6">
      {/* Report hero: back link, display headline, gold stars, KPI strip */}
      <div>
        <Link
          to="/"
          className="text-sm font-medium text-ink/70 hover:text-ink"
        >
          ← アクティビティ一覧
        </Link>
        <div className="mt-2">
          <HeroHeader detail={detail} starRating={starRating} />
        </div>
      </div>

      {/* Overall assessment report */}
      <SummaryReport section={sections?.summary} />

      {/* Time series chart with metric toggles */}
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="mb-3 font-display text-base font-semibold text-ink">
          タイムシリーズ
        </h2>
        <div className="mb-4 flex flex-wrap gap-2">
          {AVAILABLE_METRICS.map(({ key, label }) => {
            const checked = selectedMetrics.includes(key);
            // Active toggles carry the metric's semantic color (Issue #214),
            // matching its line color in the chart below.
            const color = METRIC_COLORS[key] ?? "#16213a";
            return (
              <label
                key={key}
                className={`inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors ${
                  checked
                    ? "font-medium"
                    : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                }`}
                style={
                  checked
                    ? {
                        color,
                        borderColor: `${color}4d`,
                        backgroundColor: `${color}14`,
                      }
                    : undefined
                }
              >
                <input
                  type="checkbox"
                  style={{ accentColor: color }}
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

      {/* GPS track map (placeholder when the activity has no GPS data) */}
      {track !== null && (
        <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
          <h2 className="px-5 pt-4 pb-2 font-display text-base font-semibold text-ink">
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

      {/* Splits: table + per-split narrative from the split analyst */}
      {(splits.length > 0 || sections?.split) && (
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 font-display text-base font-semibold text-ink">
            スプリット
          </h2>
          {splits.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs tracking-wide text-slate-500 uppercase">
                  <th className="px-2 py-2 text-left font-medium">#</th>
                  <th className="px-2 py-2 text-right font-medium">距離</th>
                  <th className="px-2 py-2 text-right font-medium">ペース</th>
                  <th className="px-2 py-2 text-right font-medium">心拍</th>
                  <th className="px-2 py-2 text-right font-medium">
                    ケイデンス
                  </th>
                  <th className="px-2 py-2 text-right font-medium">パワー</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-numeric text-[15px]">
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
                      {formatCadence(split.cadence)}
                    </td>
                    <td className="px-2 py-2 text-right tabular-nums">
                      {split.power ?? "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <SplitNarrative section={sections?.split} />
        </section>
      )}

      {/* Phase evaluation timeline */}
      <PhaseTimeline section={sections?.phase} />

      {/* Efficiency: structured form stats + analyst prose */}
      <EfficiencyReport
        section={sections?.efficiency}
        formEfficiency={detail.form_efficiency}
      />

      {/* Environmental impact */}
      <EnvironmentReport section={sections?.environment} />

      {/* Unknown section types degrade to key-value cards */}
      {sections &&
        unknownSectionTypes.map((type) => (
          <ReportCard key={type} title={type} section={sections[type]}>
            {(data) => <FallbackFields data={data} exclude={["metadata"]} />}
          </ReportCard>
        ))}
    </div>
  );
}
