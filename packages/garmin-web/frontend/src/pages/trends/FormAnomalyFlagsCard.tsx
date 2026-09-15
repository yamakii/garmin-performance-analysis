import { Link } from "react-router-dom";
import type { FormAnomalyFlagsResponse } from "../../types";
import { formatDateLabel } from "../../utils/format";

interface FormAnomalyFlagsCardProps {
  data: FormAnomalyFlagsResponse;
}

/**
 * "今週の注意点": the recent runs whose form metrics flagged an anomaly.
 *
 * An empty list is the normal morning, so it is one muted sentence rather than
 * a card with a "問題なし" badge — the block only takes colour when there is
 * something to act on (Morning Brief, #1120). Each flagged run states the
 * coach's leading recommendation and links to the run itself, because the next
 * question after "何かあった?" is always "どの走りで?".
 *
 * The scan window and the scanned count belong to the section heading, not
 * here: they qualify the whole block, including the empty case.
 */
export default function FormAnomalyFlagsCard({
  data,
}: FormAnomalyFlagsCardProps) {
  if (data.flags.length === 0) {
    return (
      <p className="text-[15px] leading-[1.7] text-ink-muted">
        直近のランでフォームの異常は検出されていません。
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-3">
      {data.flags.map((flag) => (
        <li
          key={flag.activity_id}
          className="rounded-md border border-warn-line bg-warn-tint px-5 py-4"
        >
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 font-mono text-[13px] text-status-warn">
            <span>{formatDateLabel(flag.activity_date)}</span>
            <span>
              異常 {flag.anomalies_detected}件
              {flag.severity_high > 0 ? `（高 ${flag.severity_high}）` : ""}
            </span>
            <Link
              to={`/activities/${flag.activity_id}`}
              className="ml-auto whitespace-nowrap"
            >
              ランを見る →
            </Link>
          </div>
          {flag.top_recommendation != null && (
            <p className="mt-2 text-[15px] leading-[1.7] text-ink">
              {flag.top_recommendation}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
