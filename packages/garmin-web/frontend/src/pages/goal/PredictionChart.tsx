import { useMemo } from "react";
import type { JSX } from "react";
import { useRacePredictionHistory } from "../../api/hooks";
import EChart from "../../components/EChart";
import SectionBlock from "../../components/SectionBlock";
import { CHART_HEIGHT } from "../trends/blockShell";
import { buildPredictionChartOption } from "./predictionChartOption";

/**
 * "予測の推移": how the predicted goal-race time has moved, against the target
 * and race day (Issue #1133).
 *
 * Supplementary to the rest of the page: a failed fetch, an athlete with no
 * goal and a database with no fitness history all render nothing at all rather
 * than an error or an empty frame — the section simply is not there.
 */
export default function PredictionChart(): JSX.Element | null {
  const { data } = useRacePredictionHistory();
  const option = useMemo(
    () => (data != null ? buildPredictionChartOption(data) : null),
    [data],
  );

  if (data == null || option == null) {
    return null;
  }

  return (
    <SectionBlock
      title="予測の推移"
      note={
        data.source === "objective"
          ? "客観VDOT換算 · 直近1年"
          : "Garmin VO2max 換算 · 直近1年"
      }
      noteMono
    >
      <EChart
        option={option}
        ariaLabel="レース予測タイムの推移グラフ"
        height={CHART_HEIGHT}
      />
    </SectionBlock>
  );
}
