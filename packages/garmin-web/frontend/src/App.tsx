import { lazy, Suspense, useEffect } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import Layout from "./components/Layout";
import { PageLoading } from "./components/PageState";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const ActivityList = lazy(() => import("./pages/ActivityList"));
const ActivityDetail = lazy(() => import("./pages/ActivityDetail"));
const Condition = lazy(() => import("./pages/Condition"));
const Performance = lazy(() => import("./pages/Performance"));
const Goal = lazy(() => import("./pages/Goal"));
const Plan = lazy(() => import("./pages/Plan"));
const WeeklyReviews = lazy(() => import("./pages/WeeklyReviews"));
const WeeklyReviewDetail = lazy(() => import("./pages/WeeklyReviewDetail"));
const NotFound = lazy(() => import("./pages/NotFound"));

/**
 * `/trends` was split into `/condition` and `/performance` (#892). Old
 * bookmarks and the Home snapshot tiles' deep links (`/trends#recovery`) land
 * on the condition page; the hash and query string are carried across so the
 * anchor still resolves.
 */
function TrendsRedirect() {
  const { hash, search } = useLocation();
  return <Navigate to={{ pathname: "/condition", hash, search }} replace />;
}

/**
 * Scroll restoration for the SPA (#914).
 *
 * A browser resets the scroll position on every document load; a client-side
 * route change does not, so following a link from halfway down the activity
 * list used to open the next page already scrolled past its heading. Landing
 * at the top on navigation is what the reader expects from a page change.
 *
 * A hash navigation is the exception: the anchor target owns the position, and
 * scrolling to the top would undo the jump to the linked section.
 */
export function ScrollToTop() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash !== "") {
      return;
    }
    window.scrollTo(0, 0);
  }, [pathname, hash]);
  return null;
}

export default function App() {
  return (
    <BrowserRouter>
      <ScrollToTop />
      <Layout>
        <Suspense fallback={<PageLoading />}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/activities" element={<ActivityList />} />
            <Route path="/activities/:id" element={<ActivityDetail />} />
            <Route path="/condition" element={<Condition />} />
            <Route path="/performance" element={<Performance />} />
            <Route path="/trends" element={<TrendsRedirect />} />
            <Route path="/goal" element={<Goal />} />
            <Route path="/plan" element={<Plan />} />
            {/* The review list left the nav for /plan (#983) but stays
                routable: the grid links into it and into each week. */}
            <Route path="/weekly-reviews" element={<WeeklyReviews />} />
            <Route
              path="/weekly-reviews/:weekStart"
              element={<WeeklyReviewDetail />}
            />
            {/* Catch-all: unknown URLs land on 404 instead of a blank page. */}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </Layout>
    </BrowserRouter>
  );
}
