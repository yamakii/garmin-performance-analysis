import { describe, expect, it } from "vitest";
import { render, screen } from "../test/utils";
import Disclosure from "./Disclosure";

/**
 * jsdom does not implement `<details>` visibility, so "collapsed" is asserted
 * through the `open` attribute — the same signal the browser uses to hide the
 * body — rather than through computed styles.
 */
function detailsFor(titleText: string): HTMLDetailsElement {
  const details = screen.getByText(titleText).closest("details");
  expect(details).not.toBeNull();
  return details as HTMLDetailsElement;
}

describe("Disclosure", () => {
  it("test_disclosure_closed_by_default", () => {
    render(
      <Disclosure title="ボトルネック">
        <p>後半の失速を抑える</p>
      </Disclosure>,
    );

    expect(detailsFor("ボトルネック").hasAttribute("open")).toBe(false);
  });

  it("test_disclosure_default_open", () => {
    render(
      <Disclosure title="ボトルネック" defaultOpen>
        <p>後半の失速を抑える</p>
      </Disclosure>,
    );

    expect(detailsFor("ボトルネック").hasAttribute("open")).toBe(true);
    expect(screen.getByText("後半の失速を抑える")).toBeInTheDocument();
  });

  it("test_disclosure_arrows_are_scoped_to_own_details", () => {
    // jsdom does not evaluate Tailwind's CSS, so this asserts the arrows are
    // scoped via a `details[open]>summary>&` arbitrary variant anchored to
    // this element's own `<details>`, rather than the ancestor-matching
    // `group-open:` that let a nested Disclosure's arrow get stuck once the
    // outer one opened (#1177).
    render(
      <Disclosure title="ボトルネック">
        <p>後半の失速を抑える</p>
      </Disclosure>,
    );

    const details = detailsFor("ボトルネック");
    const [downArrow, upArrow] = details.querySelectorAll(
      'summary span[aria-hidden="true"]',
    );

    expect(downArrow.className).not.toMatch(/group-open/);
    expect(upArrow.className).not.toMatch(/group-open/);
    expect(downArrow.className).toContain(
      "[details[open]>summary>&]:hidden",
    );
    expect(upArrow.className).toContain("hidden");
    expect(upArrow.className).toContain(
      "[details[open]>summary>&]:inline",
    );
  });
});
