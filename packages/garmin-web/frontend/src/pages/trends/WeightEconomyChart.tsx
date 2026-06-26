import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  METRIC_COLORS,
} from "../../components/chartTheme";
import { formatNumber } from "../../utils/formatNumber";
import type { WeightEconomyCoupling } from "../../types";

interface WeightEconomyChartProps {
  data: WeightEconomyCoupling;
}

const WEIGHT_SERIES = "体重 (kg)";
const EF_SERIES = "EF (易ラン)";

const WEIGHT_COLOR = "#16213a";
const EF_COLOR = METRIC_COLORS.speed;

export default function WeightEconomyChart({ data }: WeightEconomyChartProps) {
  const { series, model, note } = data;

  const option = useMemo(
    () => ({
      ...BASE_CHART_OPTION,
      tooltip: { trigger: "axis" as const },
      legend: { data: [WEIGHT_SERIES, EF_SERIES] },
      xAxis: {
        type: "category" as const,
        data: series.map((p) => p.run_date),
        ...AXIS_STYLE,
      },
      yAxis: [
        { type: "value" as const, name: "kg", scale: true, ...AXIS_STYLE },
        { type: "value" as const, name: "EF", scale: true, ...AXIS_STYLE },
      ],
      series: [
        {
          name: WEIGHT_SERIES,
          type: "line" as const,
          yAxisIndex: 0,
          smooth: true,
          connectNulls: false,
          itemStyle: { color: WEIGHT_COLOR },
          lineStyle: { color: WEIGHT_COLOR },
          data: series.map((p) => p.weight_kg),
        },
        {
          name: EF_SERIES,
          type: "line" as const,
          yAxisIndex: 1,
          smooth: true,
          connectNulls: false,
          itemStyle: { color: EF_COLOR },
          lineStyle: { color: EF_COLOR },
          data: series.map((p) => p.ef),
        },
      ],
    }),
    [series],
  );

  const isEmpty = model == null && series.length === 0;

  return (
    <section
      aria-label="体重 × ランニングエコノミー (EF)"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-semibold text-ink">
          体重 × ランニングエコノミー (EF)
        </h2>
        {model != null && (
          <span className="shrink-0 text-sm font-semibold text-ink">
            約5kg減 → +{formatNumber(model.delta_ef_per_5kg_loss, 4)} EF
          </span>
        )}
      </div>
      {isEmpty ? (
        <p className="py-8 text-center text-sm text-slate-500">
          易しいランと体重を結び付けられるデータがまだ不足しています
        </p>
      ) : (
        <>
          {model != null && (
            <p className="mb-1 text-sm text-slate-600">
              易ラン {model.n} 本の縦断回帰: 体重 約5kg減で EF{" "}
              <span className="font-semibold text-ink">
                +{formatNumber(model.delta_ef_per_5kg_loss, 4)}
              </span>{" "}
              の関連（effect size）
            </p>
          )}
          {model != null && model.collinearity_flag && (
            <p
              role="alert"
              className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700"
            >
              共線性のため、これは関連であってクリーンな因果係数ではありません。
              {note ? `（${note}）` : ""}
            </p>
          )}
          <EChart
            option={option}
            ariaLabel="体重とEF（易ラン）の二軸推移グラフ"
          />
        </>
      )}
    </section>
  );
}
