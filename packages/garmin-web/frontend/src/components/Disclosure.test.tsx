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
});
