import { BrowserRouter, Routes, Route } from "react-router-dom";
import DashboardApp from "./DashboardApp";
import LandingPage from "./pages/LandingPage";
import TriageQueuePage from "./pages/TriageQueuePage";
import PatientSurveillancePage from "./pages/PatientSurveillancePage";
import AdherenceHeatmapsPage from "./pages/AdherenceHeatmapsPage";
import "./styles.css";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/dashboard" element={<DashboardApp />}>
          <Route path="triage" element={<TriageQueuePage />} />
          <Route path="surveillance" element={<PatientSurveillancePage />} />
          <Route path="heatmaps" element={<AdherenceHeatmapsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
