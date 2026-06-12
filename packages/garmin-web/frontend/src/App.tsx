import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import ActivityList from "./pages/ActivityList";
import TrendsDashboard from "./pages/TrendsDashboard";

export default function App() {
  return (
    <BrowserRouter>
      <nav>
        <Link to="/">アクティビティ一覧</Link> | <Link to="/trends">トレンド</Link>
      </nav>
      <Routes>
        <Route path="/" element={<ActivityList />} />
        <Route path="/trends" element={<TrendsDashboard />} />
      </Routes>
    </BrowserRouter>
  );
}
