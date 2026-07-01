import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const ActivityList = lazy(() => import("./pages/ActivityList"));
const ActivityDetail = lazy(() => import("./pages/ActivityDetail"));
const TrendsDashboard = lazy(() => import("./pages/TrendsDashboard"));
const Goal = lazy(() => import("./pages/Goal"));
const WeeklyReviews = lazy(() => import("./pages/WeeklyReviews"));
const WeeklyReviewDetail = lazy(() => import("./pages/WeeklyReviewDetail"));

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
            <Route path="/trends" element={<TrendsDashboard />} />
            <Route path="/goal" element={<Goal />} />
            <Route path="/weekly-reviews" element={<WeeklyReviews />} />
            <Route
              path="/weekly-reviews/:weekStart"
              element={<WeeklyReviewDetail />}
            />
          </Routes>
        </Suspense>
      </Layout>
    </BrowserRouter>
  );
}
