import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { configureAuthSession } from "./auth/session";

configureAuthSession();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
