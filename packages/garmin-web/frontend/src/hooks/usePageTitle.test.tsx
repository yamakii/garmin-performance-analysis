import { render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { usePageTitle } from "./usePageTitle";

function Page({ title }: { title: string | undefined }) {
  usePageTitle(title);
  return <p>page</p>;
}

const ORIGINAL_TITLE = document.title;

afterEach(() => {
  document.title = ORIGINAL_TITLE;
});

describe("usePageTitle", () => {
  it("test_page_title_sets_document_title", () => {
    render(<Page title="アクティビティ一覧" />);

    expect(document.title).toBe("アクティビティ一覧 | Garmin Performance");
  });

  it("test_page_title_undefined_keeps_current_title", () => {
    document.title = "前のページ | Garmin Performance";

    // A page whose name is still loading must not flash a placeholder title.
    const { rerender } = render(<Page title={undefined} />);
    expect(document.title).toBe("前のページ | Garmin Performance");

    // ...and it takes over as soon as the name arrives.
    rerender(<Page title="Morning Run" />);
    expect(document.title).toBe("Morning Run | Garmin Performance");
  });
});
