import type { JSX } from "react";
import { Link } from "react-router-dom";
import SectionBlock from "../SectionBlock";
import { ZONE_COLORS } from "../chartTheme";
import type { RunNoteSignalNote, RunSignal, RunZoneShare } from "../../types";
import { formatNumber } from "../../utils/formatNumber";
import { zBandStyle, zDirection, zDotStyle } from "../../utils/baselineZ";

/** Heading per signal family, in reading order. */
const FAMILIES: { key: RunSignal["family"]; title: string }[] = [
  { key: "form", title: "フォーム" },
  { key: "cardio", title: "心肺" },
];

/**
 * Label / track / reading, shared by every signal row and by the axis caption
 * that names the track's two sides — they have to be one set of columns or the
 * caption would point at the wrong part of the bar.
 */
const ROW_COLUMNS = "md:grid-cols-[110px_minmax(0,1fr)_270px]";

/**
 * Metrics whose *low* side is the unfavourable one.
 *
 * A short ground contact time or a small vertical oscillation is good news; a
 * low cadence and a low power efficiency are not. The report orients `z` so
 * that positive is always the bad side, which is exactly why the prose cannot
 * read the side off the sign — it has to know the metric's polarity.
 */
const LOW_SIDE_IS_WORSE = new Set(["cadence", "power"]);

/** Decimals per display unit: whole beats and milliseconds, tenths elsewhere. */
const UNIT_DECIMALS: Record<string, number> = { ms: 0, bpm: 0, spm: 0 };

/** Which side of the band is this metric's bad one. */
export function higherIsWorse(signal: RunSignal): boolean {
  return signal.higher_is_worse ?? !LOW_SIDE_IS_WORSE.has(signal.metric);
}

/** "高い側" / "低い側" — the side `z` points to for this metric. */
function sideLabel(signal: RunSignal): string {
  const towardsBadSide = (signal.z ?? 0) > 0;
  return towardsBadSide === higherIsWorse(signal) ? "高い側" : "低い側";
}

/**
 * How today's reading sits against the athlete's own range, in words.
 *
 * The side is named rather than implied, because the unfavourable side is not
 * the same side for every metric: 範囲外（低い側） is the *bad* news for
 * cadence and the good news for ground contact time. A favourable outlier is
 * never dressed up as a warning — it reads 良い側に外れ and takes no colour.
 */
export function tailText(signal: RunSignal): string {
  switch (signal.status) {
    case "within":
      return "いつもの範囲";
    case "edge":
      return `${sideLabel(signal)}の端`;
    case "outside":
      return signal.adverse ? `範囲外（${sideLabel(signal)}）` : "良い側に外れ";
    default:
      return "判定対象外";
  }
}

/** "262ms · 範囲外（高い側） 248–259" — the row's right-hand column. */
export function readingText(signal: RunSignal): string {
  const decimals = UNIT_DECIMALS[signal.unit] ?? 1;
  const today =
    signal.today != null
      ? `${formatNumber(signal.today, decimals)}${signal.unit}`
      : "-";
  const band =
    signal.normal_low != null && signal.normal_high != null
      ? ` ${formatNumber(signal.normal_low, decimals)}–${formatNumber(
          signal.normal_high,
          decimals,
        )}`
      : "";
  return `${today} · ${tailText(signal)}${band}`;
}

function SignalRow({
  signal,
  note,
}: {
  signal: RunSignal;
  note: string | null;
}): JSX.Element {
  const adverse = signal.adverse && signal.status === "outside";
  // The report already orients `z` so that positive is the unfavourable side,
  // whatever the metric's own polarity is — hence `higherIsWorse = true` here,
  // where the wellness panel has to apply each metric's polarity itself.
  const dot = zDotStyle({
    z: signal.status === "insufficient" ? null : signal.z,
    direction: zDirection(signal.z, true),
  });
  const toneClass = adverse ? "text-status-warn" : "";
  return (
    <li className="flex flex-col gap-1.5 py-2">
      <div
        className={`grid grid-cols-[minmax(0,1fr)] items-center gap-x-4 gap-y-1 ${ROW_COLUMNS}`}
      >
        <span className={`text-[13px] text-ink-soft ${toneClass}`}>
          {signal.label_ja}
        </span>
        {/* The track: ±3σ wide, the centre is the athlete's own normal, the
            shaded band is the ±2σ they usually fall inside, and the right half
            is always the unfavourable side whichever way this metric happens
            to read. A row with no reading keeps the centre line only. */}
        <span
          aria-hidden="true"
          data-part="track"
          className="relative block h-2.5 bg-well"
        >
          {dot != null && (
            <span
              data-part="band"
              className="absolute inset-y-0 bg-hairline"
              style={zBandStyle()}
            />
          )}
          <span className="absolute inset-y-0 left-1/2 w-px bg-ink" />
          {dot != null && (
            <span
              data-part="dot"
              className={`absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-sm ${
                adverse ? "bg-status-warn" : "bg-ink"
              }`}
              style={dot}
            />
          )}
        </span>
        <span
          className={`font-mono text-xs whitespace-nowrap md:text-right ${
            adverse ? "font-bold text-status-warn" : "text-ink-muted"
          }`}
        >
          {readingText(signal)}
        </span>
      </div>
      {signal.status === "insufficient" && signal.reason != null && (
        <p className="font-mono text-[11px] text-ink-muted">{signal.reason}</p>
      )}
      {note != null && (
        <p className="border-l-2 border-warn-line pl-3 text-[15px] leading-[1.7] text-ink-soft">
          {note}
        </p>
      )}
    </li>
  );
}

/** The share of the run spent in each Garmin native zone, as one bar. */
function ZoneBar({ zones }: { zones: RunZoneShare[] }): JSX.Element | null {
  const shown = zones.filter((zone) => zone.pct > 0);
  if (shown.length === 0) {
    return null;
  }
  return (
    <div className="mt-2 flex flex-col gap-2">
      <span
        aria-label="心拍ゾーン分布"
        role="img"
        className="flex h-2.5 w-full overflow-hidden bg-well"
      >
        {shown.map((zone) => (
          <span
            key={zone.zone}
            style={{
              width: `${zone.pct}%`,
              backgroundColor: ZONE_COLORS[zone.zone - 1] ?? ZONE_COLORS[0],
            }}
          />
        ))}
      </span>
      <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs text-ink-muted">
        {shown.map((zone) => (
          <span key={zone.zone}>
            Z{zone.zone} {formatNumber(zone.pct, 0)}%
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * What the track's two sides mean, written out once above the first one.
 *
 * It sits in the track's own column so each caption lands over the part of the
 * bar it names, and it is dropped below `md` along with the columns — stacked,
 * the rows are read one at a time and the words in each reading already say
 * which side it fell on.
 */
function AxisCaption(): JSX.Element {
  return (
    <span
      aria-hidden="true"
      className="hidden justify-between font-mono text-[11px] text-ink-muted md:flex"
    >
      <span>← 良い側</span>
      <span>いつもの範囲</span>
      <span>悪い側 →</span>
    </span>
  );
}

/**
 * いつもと比べて (#1252): every metric of the run against the athlete's own
 * normal range, grouped into form and cardio.
 *
 * There is no score and no star here. The question the block answers is "was
 * this normal for me?", and the answer is a position on a track plus the words
 * for it. Only an *adverse* excursion takes colour: an unusually short ground
 * contact time is not a thing to warn about, and tinting it would teach the
 * reader to ignore the tint.
 */
export default function NormalRangeRows({
  id,
  signals,
  zones,
  notes,
}: {
  id?: string;
  signals: RunSignal[];
  zones: RunZoneShare[];
  notes: RunNoteSignalNote[];
}): JSX.Element | null {
  if (signals.length === 0 && zones.length === 0) {
    return null;
  }
  const noteOf = new Map(notes.map((note) => [note.signal, note.text]));
  const groups = FAMILIES.map(({ key, title }) => ({
    key,
    title,
    rows: signals.filter((signal) => signal.family === key),
  })).filter((group) => group.rows.length > 0);

  return (
    <SectionBlock id={id} title="いつもと比べて">
      <div className="flex flex-col gap-6">
        {groups.map(({ key, title, rows }, index) => {
          return (
            <div key={key}>
              <div
                className={`grid grid-cols-[minmax(0,1fr)] items-baseline gap-x-4 ${ROW_COLUMNS}`}
              >
                <h3 className="font-mono text-xs text-ink-muted">{title}</h3>
                {/* Named once, over the first track: without it the dot has a
                    position but no meaning — which side is the bad one, and
                    where the athlete's usual range ends (#1270). */}
                {index === 0 && <AxisCaption />}
              </div>
              <ul className="mt-1 divide-y divide-hairline">
                {rows.map((signal) => (
                  <SignalRow
                    key={signal.metric}
                    signal={signal}
                    note={
                      signal.adverse && signal.status === "outside"
                        ? (noteOf.get(signal.metric) ?? null)
                        : null
                    }
                  />
                ))}
              </ul>
            </div>
          );
        })}
        <div>
          <h3 className="font-mono text-xs text-ink-muted">心拍ゾーン</h3>
          <ZoneBar zones={zones} />
          <Link to="/performance" className="mt-3 block font-mono text-[13px]">
            長期の推移を見る →
          </Link>
        </div>
      </div>
    </SectionBlock>
  );
}
