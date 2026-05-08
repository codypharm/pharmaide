import { useState } from "react";
import DashboardApp from "./DashboardApp";
import LandingPage from "./pages/LandingPage";
import "./styles.css";

function App() {
  const [isDashboardOpen, setIsDashboardOpen] = useState(false);

  if (isDashboardOpen) {
    return <DashboardApp />;
  }

  return <LandingPage onEnterDashboard={() => setIsDashboardOpen(true)} />;
}

export default App;
