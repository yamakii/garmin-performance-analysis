import { lazy, Suspense } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import Layout from "./components/Layout";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const ActivityList = lazy(() => import("./pages/ActivityList"));
const ActivityDetail = lazy(() => import("./pages/ActivityDetail"));
const Condition = lazy(() => import("./pages/Condition"));
const Performance = lazy(() => import("./pages/Performance"));
const Goal = lazy(() => import("./pages/Goal"));
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

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Suspense
          fallback={
            <div className="py-12 text-center text-sm text-slate-500">
              読み込み中...
            </div>
          }
        >
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/activities" element={<ActivityList />} />
            <Route path="/activities/:id" element={<ActivityDetail />} />
            <Route path="/condition" element={<Condition />} />
            <Route path="/performance" element={<Performance />} />
            <Route path="/trends" element={<TrendsRedirect />} />
            <Route path="/goal" element={<Goal />} />
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
