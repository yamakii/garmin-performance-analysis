import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Adherence } from "../../types";
import AdherenceChip, { adherenceTone } from "./AdherenceChip";

function adherence(overrides: Partial<Adherence> = {}): Adherence {
  return {
    prescribed: 0,
    done: 0,
    replaced: 0,
    skipped: 0,
    pending: 0,
    ...overrides,
  };
}

describe("AdherenceChip", () => {
  it("test_adherence_chip_good_tone", () => {
    // 3 of 4 prescribed, the 4th still ahead: every resolved session was done.
    render(
      <AdherenceChip
        adherence={adherence({ prescribed: 4, done: 3, pending: 1 })}
      />,
    );

    const chip = screen.getByText("3/4 実施");
    expect(chip).toHaveClass("text-status-good");
  });

  it("test_adherence_chip_bad_tone", () => {
    render(
      <AdherenceChip
        adherence={adherence({ prescribed: 4, done: 1, skipped: 3 })}
      />,
    );

    const chip = screen.getByText("1/4 実施");
    expect(chip).toHaveClass("text-status-bad");
  });

  it("warns in between and stays neutral before anything resolves", () => {
    expect(
      adherenceTone(adherence({ prescribed: 4, done: 2, skipped: 2 })),
    ).toBe("warn");
    // Nothing has happened yet — unfinished is not failing.
    expect(adherenceTone(adherence({ prescribed: 4, pending: 4 }))).toBe(
      "info",
    );
  });

  it("labels an unplanned week instead of showing 0/0", () => {
    render(<AdherenceChip adherence={adherence()} />);

    expect(screen.getByText("未処方")).toBeInTheDocument();
  });
});
