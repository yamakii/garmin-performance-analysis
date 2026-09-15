import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import VitalsRow, { type VitalItem } from "./VitalsRow";

const ITEMS: VitalItem[] = [
  { label: "HRV 夜間", value: "51", unit: "ms", note: "基準内 · 55–65" },
  {
    label: "安静時心拍",
    value: "48",
    unit: "bpm",
    note: "+3 · 基準外",
    noteTone: "warn",
    to: "/condition#recovery",
  },
  { label: "睡眠 / 準備度", value: "74 / 68" },
  {
    label: "負荷 ACWR",
    value: "1.02",
    note: "最適 · 週 26.4km",
    to: "/condition#training-load",
  },
];

describe("VitalsRow", () => {
  it("test_vitals_row_links_and_warn_note", () => {
    render(
      <MemoryRouter>
        <VitalsRow items={ITEMS} ariaLabel="今朝の数値" />
      </MemoryRouter>,
    );

    const row = screen.getByRole("region", { name: "今朝の数値" });
    expect(row).toBeInTheDocument();

    // A cell with `to` is the link; a cell without one is plain text.
    const rhr = screen.getByRole("link", { name: /安静時心拍/ });
    expect(rhr).toHaveAttribute("href", "/condition#recovery");
    expect(rhr).toHaveTextContent("48bpm");
    expect(
      screen.queryByRole("link", { name: /HRV 夜間/ }),
    ).not.toBeInTheDocument();

    // An adverse note is bold and 注意-coloured; a neutral one stays muted.
    expect(screen.getByText("+3 · 基準外")).toHaveClass(
      "font-bold",
      "text-status-warn",
    );
    expect(screen.getByText("基準内 · 55–65")).toHaveClass("text-ink-muted");
  });

  it("sizes the values and the grid from its props", () => {
    const { container, rerender } = render(
      <MemoryRouter>
        <VitalsRow items={ITEMS} ariaLabel="今朝の数値" />
      </MemoryRouter>,
    );
    expect(container.firstElementChild).toHaveClass("md:grid-cols-4");
    expect(screen.getByText("1.02")).toHaveClass("text-[30px]", "font-mono");

    rerender(
      <MemoryRouter>
        <VitalsRow
          items={ITEMS.slice(0, 3)}
          ariaLabel="効率"
          id="efficiency"
          columns={3}
          size="lg"
        />
      </MemoryRouter>,
    );
    const row = screen.getByRole("region", { name: "効率" });
    expect(row).toHaveAttribute("id", "efficiency");
    expect(row).toHaveClass("md:grid-cols-3");
    expect(screen.getByText("74 / 68")).toHaveClass("text-[40px]");
  });

  it("test_vitals_row_small_size", () => {
    render(
      <MemoryRouter>
        <VitalsRow
          items={ITEMS.slice(0, 3)}
          ariaLabel="フォーム指標"
          columns={3}
          size="sm"
        />
      </MemoryRouter>,
    );

    // Nested in a report card, the numbers support the prose around them
    // rather than heading the page (#1153).
    expect(screen.getByText("74 / 68")).toHaveClass("text-[28px]", "font-mono");
  });
});
