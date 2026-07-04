import StatusBadge from "../../components/StatusBadge";
import type { FormAnomalyFlagsResponse } from "../../types";

interface FormAnomalyFlagsCardProps {
  data: FormAnomalyFlagsResponse;
}

/**
 * "今週の注意点" card: surfaces recent runs whose form metrics flagged anomalies.
 *
 * The roll-up scans the trailing `weeks` of runs; an empty list is a positive
 * signal ("問題なし"). The scanned-count footnote makes any `max_activities`
 * truncation explicit instead of silently hiding older runs.
 */
export default function FormAnomalyFlagsCard({
  data,
}: FormAnomalyFlagsCardProps) {
  const hasFlags = data.flags.length > 0;

  return (
    <section
      aria-label="今週の注意点"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-semibold text-ink">
          今週の注意点
        </h2>
        <StatusBadge tone={hasFlags ? "warn" : "good"}>
          {hasFlags ? `${data.flags.length}件` : "問題なし"}
        </StatusBadge>
      </div>

      {hasFlags ? (
        <ul className="flex flex-col gap-3">
          {data.flags.map((flag) => (
            <li
              key={flag.activity_id}
              className="rounded-lg bg-slate-50 px-3 py-2"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold text-ink">
                  {flag.activity_date}
                </span>
                <span className="text-xs text-slate-500">
                  異常イベント {flag.anomalies_detected}件
                  {flag.severity_high > 0 ? `（高 ${flag.severity_high}）` : ""}
                </span>
              </div>
              {flag.top_recommendation ? (
                <p className="mt-1 text-sm text-slate-600">
                  {flag.top_recommendation}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="py-4 text-sm text-slate-500">
          直近のランでフォームの異常は検出されていません。
        </p>
      )}

      <p className="mt-3 text-xs text-slate-400">
        直近{data.weeks}週・{data.scanned}件のランを走査
        {data.limited ? "（上限により一部のみ）" : ""}
      </p>
    </section>
  );
}
