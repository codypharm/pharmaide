import { BrowserRouter, Routes, Route } from "react-router-dom";
import DashboardApp from "./DashboardApp";
import LandingPage from "./pages/LandingPage";
import TriageQueuePage from "./pages/TriageQueuePage";
import PatientManagementPage from "./pages/PatientManagementPage";
import AdherenceHeatmapsPage from "./pages/AdherenceHeatmapsPage";
import KnowledgeBasePage from "./pages/KnowledgeBasePage";
import SystemAuditsPage from "./pages/SystemAuditsPage";
import NewTreatmentPage from "./pages/NewTreatmentPage";
import PharmacistProfilePage from "./pages/PharmacistProfilePage";
import "./styles.css";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/dashboard" element={<DashboardApp />}>
          <Route path="triage" element={<TriageQueuePage />} />
          <Route path="surveillance" element={<PatientManagementPage />} />
          <Route path="heatmaps" element={<AdherenceHeatmapsPage />} />
          <Route path="knowledge" element={<KnowledgeBasePage />} />
          <Route path="audits" element={<SystemAuditsPage />} />
          <Route path="new-treatment" element={<NewTreatmentPage />} />
          <Route path="profile" element={<PharmacistProfilePage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
