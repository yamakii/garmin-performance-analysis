import { describe, expect, it } from "vitest";
import * as client from "./client";

describe("api client surface", () => {
  it("test_fetch_weekly_review_removed", () => {
    // `fetchWeeklyReview` (single week) had no callers: the list view uses
    // fetchWeeklyReviews and the detail view uses fetchWeeklyReviewVersions.
    expect(Object.keys(client)).not.toContain("fetchWeeklyReview");
    expect(Object.keys(client)).toContain("fetchWeeklyReviews");
    expect(Object.keys(client)).toContain("fetchWeeklyReviewVersions");
  });
});
