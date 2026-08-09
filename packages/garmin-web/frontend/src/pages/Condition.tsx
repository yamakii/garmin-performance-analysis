import {
  useBodyCompositionTrend,
  useFormAnomalyFlags,
  useRecoveryStatus,
  useRecoveryTrend,
  useTrainingLoad,
  useWellnessBaselineDeviation,
} from "../api/hooks";
import QueryBoundary from "../components/QueryBoundary";
import SectionHeading from "../components/SectionHeading";
import { usePageTitle } from "../hooks/usePageTitle";
import BodyCompositionChart from "./trends/BodyCompositionChart";
import ConditionCard from "./trends/ConditionCard";
import FormAnomalyFlagsCard from "./trends/FormAnomalyFlagsCard";
import RecoveryPanel from "./trends/RecoveryPanel";
import TrainingLoadBlock from "./trends/TrainingLoadBlock";
import WellnessBaselineChart from "./trends/WellnessBaselineChart";

/**
 * "今の体の状態は?" — everything that describes the athlete's current readiness:
 * this week's cautions, today's condition, recovery, personal-baseline
 * deviation, training load and body composition.
 *
 * Split out of the 16-card `/trends` mega-page (#892) so one page answers one
 * question; the "速くなっているか?" metrics moved to `/performance`.
 *
 * Every card owns its own query and its own failure: `QueryBoundary` turns a
 * pending query into a skeleton and a failed one into a retryable in-card
 * alert, so a single broken endpoint no longer blanks the page behind an
 * all-or-nothing banner.
 */

export default function Condition() {
  usePageTitle("コンディション");
  const formAnomalyFlagsQuery = useFormAnomalyFlags();
  const recoveryStatusQuery = useRecoveryStatus();
  const recoveryQuery = useRecoveryTrend();
  const wellnessBaselineQuery = useWellnessBaselineDeviation();
  const trainingLoadQuery = useTrainingLoad();
  const bodyCompositionQuery = useBodyCompositionTrend();

  return (
    <div className="space-y-8">
      <SectionHeading eyebrow="Condition" title="今の体の状態" />

      {/*
        Alert band: "今, 何を見るべきか" leads the page, full width and outside
        the metric grid. The `form-anomaly` / `recovery` / `training-load`
        anchors are the deep-link targets of the Home snapshot tiles, which
        keep working across the `/trends` redirect. `scroll-mt-20` keeps the
        target clear of the sticky header after a jump.
      */}
      <div id="form-anomaly" className="scroll-mt-20">
        <QueryBoundary label="今週の注意点" query={formAnomalyFlagsQuery}>
          {(data) => <FormAnomalyFlagsCard data={data} />}
        </QueryBoundary>
      </div>

      <div className="stagger-in grid gap-4 md:grid-cols-2">
        <QueryBoundary label="当日コンディション" query={recoveryStatusQuery}>
          {(data) => <ConditionCard data={data} />}
        </QueryBoundary>

        <div id="recovery" className="scroll-mt-20">
          <QueryBoundary label="回復トレンド" query={recoveryQuery}>
            {(data) => <RecoveryPanel data={data} />}
          </QueryBoundary>
        </div>

        <QueryBoundary
          label="個人ベースライン逸脱"
          query={wellnessBaselineQuery}
        >
          {(data) => <WellnessBaselineChart data={data} />}
        </QueryBoundary>

        <div id="training-load" className="scroll-mt-20">
          <QueryBoundary label="訓練負荷" query={trainingLoadQuery}>
            {(data) => <TrainingLoadBlock data={data} />}
          </QueryBoundary>
        </div>

        <QueryBoundary label="体組成" query={bodyCompositionQuery}>
          {(data) => <BodyCompositionChart data={data} />}
        </QueryBoundary>
      </div>
    </div>
  );
}
