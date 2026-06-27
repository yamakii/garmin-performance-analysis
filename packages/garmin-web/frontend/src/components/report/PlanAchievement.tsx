import type { JSX, ReactNode } from "react";

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

function asBool(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function asObject(value: unknown): Record<string, unknown> | null {
  return value != null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/** Renders a checkmark / cross achievement mark, or nothing when the flag is absent. */
function AchievementMark({ achieved }: { achieved: boolean | null }) {
  if (achieved == null) {
    return null;
  }
  return achieved ? (
    <span className="ml-1.5 font-semibold text-emerald-600">✓</span>
  ) : (
    <span className="ml-1.5 font-semibold text-rose-500">✗</span>
  );
}

/** A target-vs-actual comparison line with an optional achievement mark. */
function CompareLine({
  label,
  target,
  actual,
  achieved,
}: {
  label: string;
  target: string | null;
  actual: string | null;
  achieved: boolean | null;
}) {
  if (target == null && actual == null) {
    return null;
  }
  return (
    <p className="text-sm text-slate-700">
      <span className="font-semibold text-indigo-700">{label}</span>
      <span className="ml-1.5 tabular-nums">
        {target != null && <span>目標 {target}</span>}
        {target != null && actual != null && (
          <span className="mx-1 text-slate-400">→</span>
        )}
        {actual != null && <span>実績 {actual}</span>}
      </span>
      <AchievementMark achieved={achieved} />
    </p>
  );
}

/**
 * Achievement card for the structured `plan_achievement` object: a Japanese
 * workout-type badge, target-vs-actual HR / pace comparison lines with
 * achievement marks, and an evaluation paragraph. Renders only present
 * fields and never exposes raw English keys. Returns null for non-object input.
 */
export default function PlanAchievement({
  data,
}: {
  data: Record<string, unknown>;
}): JSX.Element | null {
  if (data == null || typeof data !== "object" || Array.isArray(data)) {
    return null;
  }

  const descriptionJa = asString(data.description_ja);

  const targets = asObject(data.targets);
  const actuals = asObject(data.actuals);

  const targetHr = asString(targets?.hr);
  const actualHr = asString(actuals?.hr);
  const targetPace = asString(targets?.pace);
  const actualPace = asString(actuals?.pace);

  const hrAchieved = asBool(data.hr_achieved);
  const paceAchieved = asBool(data.pace_achieved);

  const evaluation = asString(data.evaluation);

  const lines: ReactNode[] = [];
  if (targetHr != null || actualHr != null) {
    lines.push(
      <CompareLine
        key="hr"
        label="HR"
        target={targetHr}
        actual={actualHr}
        achieved={hrAchieved}
      />,
    );
  }
  if (targetPace != null || actualPace != null) {
    lines.push(
      <CompareLine
        key="pace"
        label="ペース"
        target={targetPace}
        actual={actualPace}
        achieved={paceAchieved}
      />,
    );
  }

  return (
    <div className="rounded-lg border border-indigo-100 bg-indigo-50/40 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-xs font-semibold tracking-wide text-indigo-700 uppercase">
          プラン達成度
        </h3>
        {descriptionJa != null && (
          <span className="rounded-full bg-indigo-600 px-2.5 py-0.5 text-xs font-semibold text-white">
            {descriptionJa}
          </span>
        )}
      </div>
      {lines.length > 0 && <div className="mt-3 space-y-1.5">{lines}</div>}
      {evaluation != null && (
        <p className="mt-3 text-sm leading-relaxed text-slate-700">
          {evaluation}
        </p>
      )}
    </div>
  );
}
