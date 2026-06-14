import { BrowserRouter, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import ActivityDetail from "./pages/ActivityDetail";
import ActivityList from "./pages/ActivityList";
import Goal from "./pages/Goal";
import TrendsDashboard from "./pages/TrendsDashboard";
import WeeklyReviewDetail from "./pages/WeeklyReviewDetail";
import WeeklyReviews from "./pages/WeeklyReviews";

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<ActivityList />} />
          <Route path="/activities/:id" element={<ActivityDetail />} />
          <Route path="/trends" element={<TrendsDashboard />} />
          <Route path="/goal" element={<Goal />} />
          <Route path="/weekly-reviews" element={<WeeklyReviews />} />
          <Route
            path="/weekly-reviews/:weekStart"
            element={<WeeklyReviewDetail />}
          />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
