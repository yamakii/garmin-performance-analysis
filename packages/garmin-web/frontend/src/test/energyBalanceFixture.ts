import type {
  EnergyBalance,
  EnergyBalanceDay,
  EnergyBalanceTarget,
  EnergyBalanceWindow,
} from "../types";

/** The observed week (2026-09-19..25) plus today's open day, as the reader serves it. */
const DAYS: [string, number, number, string][] = [
  ["2026-09-19", 1866, 3039, "settled"],
  ["2026-09-20", 2009, 2090, "provisional"],
  ["2026-09-21", 1777, 1984, "provisional"],
  ["2026-09-22", 1505, 2316, "provisional"],
  ["2026-09-23", 1915, 2519, "provisional"],
  ["2026-09-24", 2516, 2265, "provisional"],
  ["2026-09-25", 1574, 2235, "provisional"],
];

function day(
  date: string,
  intake: number,
  expenditure: number,
  status: string,
): EnergyBalanceDay {
  return {
    date,
    intake_kcal: intake,
    expenditure_kcal: expenditure,
    balance_kcal: intake - expenditure,
    intake_status: status,
    expenditure_status: "ok",
    used: true,
    in_window: true,
    confirmation: null,
  };
}

interface Overrides {
  days?: EnergyBalanceDay[];
  window?: Partial<EnergyBalanceWindow>;
  target?: Partial<EnergyBalanceTarget>;
  logging?: Partial<EnergyBalance["logging"]>;
  calibration?: Partial<EnergyBalance["calibration"]>;
}

/**
 * A 維持-block week at -469 kcal/day, deeper than the band (the #1434 real
 * week). Overrides replace the named fields of each block.
 */
export function energyBalanceFixture(overrides: Overrides = {}): EnergyBalance {
  const days = overrides.days ?? [
    ...DAYS.map(([date, intake, expenditure, status]) =>
      day(date, intake, expenditure, status),
    ),
    {
      ...day("2026-09-26", 909, 1306, "in_progress"),
      expenditure_status: "in_progress",
      used: false,
      in_window: false,
    },
  ];
  return {
    end_date: "2026-09-25",
    as_of: "2026-09-26",
    window_days: 7,
    days,
    window: {
      status: "ok",
      paired_days: 7,
      required_days: 5,
      mean_intake_kcal: 1880,
      mean_expenditure_kcal: 2350,
      mean_balance_kcal: -469,
      provisional_days: 6,
      excluded: [],
      ...overrides.window,
    },
    logging: {
      first_logged_date: "2026-09-17",
      last_logged_date: "2026-09-25",
      days_since_last_log: 0,
      lapsed: false,
      ...overrides.logging,
    },
    target: {
      weight_mode: "維持",
      block_id: 15,
      crosses_block_boundary: false,
      band_kcal: [-150, 150],
      verdict: "deeper_than_target",
      reason: null,
      basis: "logged",
      calibration_status: "insufficient",
      ...overrides.target,
    },
    calibration: {
      status: "insufficient",
      reason: "too_few_paired_days",
      paired_days: 9,
      n_weighins: 18,
      ...overrides.calibration,
    },
    weight: { recent_median_kg: 78.0, n_weighins: 18, slope_kg_per_week: -0.28 },
  };
}
