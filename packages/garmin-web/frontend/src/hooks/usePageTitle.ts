import { useEffect } from "react";

/** Trailing brand, so a tab is identifiable as this app at a glance. */
const SUFFIX = "Garmin Performance";

/**
 * Set `document.title` to "{title} | Garmin Performance" while a page is
 * mounted (WCAG 2.4.2). A single-page app never reloads the document, so
 * without this every route keeps the index.html title and neither the tab, the
 * browser history nor a screen reader's page announcement can tell them apart.
 *
 * `undefined` (data not loaded yet) leaves the current title alone rather than
 * flashing a placeholder, and nothing is restored on unmount: the next page
 * sets its own title, which is the only transition that exists here.
 */
export function usePageTitle(title: string | undefined): void {
  useEffect(() => {
    if (title == null || title === "") {
      return;
    }
    document.title = `${title} | ${SUFFIX}`;
  }, [title]);
}
