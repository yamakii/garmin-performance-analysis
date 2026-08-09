import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import VersionSelect, { STALE_VERSION_BADGE } from "./VersionSelect";

const OPTIONS = [
  { key: "2", stamp: "2026-06-22T09:00:00" },
  { key: "1", stamp: "2026-06-21T21:30:00" },
];

describe("VersionSelect", () => {
  /** The raw wire stamp ("...T09:00:00") never reaches the reader (#915). */
  it("test_version_option_readable_datetime", () => {
    render(
      <VersionSelect
        id="v"
        options={OPTIONS}
        selectedIndex={0}
        onSelect={vi.fn()}
      />,
    );

    const options = screen.getAllByRole("option");
    expect(options[0]).toHaveTextContent("2026-06-22 09:00（最新）");
    expect(options[0].textContent).not.toContain("T");
    expect(options[1]).toHaveTextContent("2026-06-21 21:30");
    expect(options[1].textContent).not.toContain("最新");
  });

  it("test_stale_version_badge", () => {
    const latest = render(
      <VersionSelect
        id="v"
        options={OPTIONS}
        selectedIndex={0}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.queryByText(STALE_VERSION_BADGE)).not.toBeInTheDocument();
    latest.unmount();

    render(
      <VersionSelect
        id="v"
        options={OPTIONS}
        selectedIndex={1}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText(STALE_VERSION_BADGE)).toBeInTheDocument();
  });

  it("renders nothing when there is only one version", () => {
    const { container } = render(
      <VersionSelect
        id="v"
        options={[OPTIONS[0]]}
        selectedIndex={0}
        onSelect={vi.fn()}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("labels a version with no timestamp instead of showing a blank option", () => {
    render(
      <VersionSelect
        id="v"
        options={[OPTIONS[0], { key: "0", stamp: null }]}
        selectedIndex={0}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getAllByRole("option")[1]).toHaveTextContent("日時不明");
  });
});
