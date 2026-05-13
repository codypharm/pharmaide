import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import DashboardApp from "./DashboardApp";
import LandingPage from "./pages/LandingPage";
import TriageQueuePage from "./pages/TriageQueuePage";
import PatientManagementPage from "./pages/PatientManagementPage";
import AdherenceHeatmapsPage from "./pages/AdherenceHeatmapsPage";
import KnowledgeBasePage from "./pages/KnowledgeBasePage";
import KnowledgeDocumentPage from "./pages/KnowledgeDocumentPage";
import SystemAuditsPage from "./pages/SystemAuditsPage";
import NewTreatmentPage from "./pages/NewTreatmentPage";
import IngestionsPage from "./pages/IngestionsPage";
import TreatmentDetailPage from "./pages/TreatmentDetailPage";
import PharmacistProfilePage from "./pages/PharmacistProfilePage";
import "./styles.css";

function App() {
  return (
    <BrowserRouter>
      <Toaster position="top-right" richColors closeButton expand />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/dashboard" element={<DashboardApp />}>
          <Route path="triage" element={<TriageQueuePage />} />
          <Route path="surveillance" element={<PatientManagementPage />} />
          <Route path="heatmaps" element={<AdherenceHeatmapsPage />} />
          <Route path="knowledge" element={<KnowledgeBasePage />} />
          <Route path="knowledge/:id" element={<KnowledgeDocumentPage />} />
          <Route path="audits" element={<SystemAuditsPage />} />
          <Route path="new-treatment" element={<NewTreatmentPage />} />
          <Route path="ingestions" element={<IngestionsPage />} />
          <Route path="treatments/:id" element={<TreatmentDetailPage />} />
          <Route path="profile" element={<PharmacistProfilePage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
