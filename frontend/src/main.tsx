import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { configureAuthSession } from "./auth/session";

const authSessionState = configureAuthSession();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App authSessionState={authSessionState} />
  </StrictMode>,
);
