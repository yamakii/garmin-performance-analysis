import { BrowserRouter, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import ActivityDetail from "./pages/ActivityDetail";
import ActivityList from "./pages/ActivityList";
import TrendsDashboard from "./pages/TrendsDashboard";

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<ActivityList />} />
          <Route path="/activities/:id" element={<ActivityDetail />} />
          <Route path="/trends" element={<TrendsDashboard />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
