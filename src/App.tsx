import { Activity, Flame, Table2 } from "lucide-react";
import { useState } from "react";
import AdherenceHeatmapsPage from "./pages/AdherenceHeatmapsPage";
import PatientSurveillancePage from "./pages/PatientSurveillancePage";
import TriageQueuePage from "./pages/TriageQueuePage";
import type { Page } from "./types";
import "./styles.css";

const pageTitleByRoute: Record<Page, string> = {
  triage: "Triage Queue",
  surveillance: "Patient Surveillance",
  heatmaps: "Adherence Heatmaps",
};

function App() {
  const [activePage, setActivePage] = useState<Page>("triage");
  const [isPrivacyMode, setIsPrivacyMode] = useState(false);
  const pageTitle = pageTitleByRoute[activePage];

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="sidebar__header">
          <p className="label-caps">PharmaAide</p>
          <p>Clinical Operations</p>
        </div>
        <nav className="sidebar__nav">
          <a
            aria-current={activePage === "triage" ? "page" : undefined}
            className={`sidebar__link ${activePage === "triage" ? "sidebar__link--active" : ""}`}
            href="#triage"
            onClick={() => setActivePage("triage")}
          >
            <Flame aria-hidden="true" size={18} strokeWidth={2.1} />
            Triage Queue
          </a>
          <a
            aria-current={activePage === "surveillance" ? "page" : undefined}
            className={`sidebar__link ${activePage === "surveillance" ? "sidebar__link--active" : ""}`}
            href="#surveillance"
            onClick={() => setActivePage("surveillance")}
          >
            <Activity aria-hidden="true" size={18} strokeWidth={2.1} />
            Patient Surveillance
          </a>
          <a
            aria-current={activePage === "heatmaps" ? "page" : undefined}
            className={`sidebar__link ${activePage === "heatmaps" ? "sidebar__link--active" : ""}`}
            href="#heatmaps"
            onClick={() => setActivePage("heatmaps")}
          >
            <Table2 aria-hidden="true" size={18} strokeWidth={2.1} />
            Adherence Heatmaps
          </a>
        </nav>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <h1>{pageTitle}</h1>
          </div>
          <label className="privacy-switch">
            <span className="privacy-switch__label">Privacy Mode</span>
            <input
              checked={isPrivacyMode}
              className="privacy-switch__input"
              onChange={(event) => setIsPrivacyMode(event.target.checked)}
              role="switch"
              type="checkbox"
            />
            <span className="privacy-switch__track" aria-hidden="true">
              <span className="privacy-switch__thumb" />
            </span>
          </label>
        </header>

        {activePage === "triage" ? <TriageQueuePage isPrivacyMode={isPrivacyMode} /> : null}
        {activePage === "surveillance" ? <PatientSurveillancePage isPrivacyMode={isPrivacyMode} /> : null}
        {activePage === "heatmaps" ? <AdherenceHeatmapsPage isPrivacyMode={isPrivacyMode} /> : null}
      </main>
    </div>
  );
}

export default App;
