import { setAuthTokenProvider } from "../api/client";
import { type FrontendConfig, getFrontendConfig } from "../config";
import { createGcipAuthAdapter } from "./gcip";

export type AuthSessionState =
  | { status: "disabled" }
  | { status: "ready"; mode: "gcip"; adapter: AuthTokenAdapter }
  | { status: "missing_adapter"; mode: "gcip" };

export type AuthTokenAdapter = {
  getIdToken: () => Promise<string | null> | string | null;
  signInWithEmailPassword?: (email: string, password: string) => Promise<void>;
  signOut?: () => Promise<void>;
  currentUserEmail?: () => string | null;
};

export function configureAuthSession(
  config: FrontendConfig = getFrontendConfig(),
  adapter: AuthTokenAdapter | null = config.gcip ? createGcipAuthAdapter(config.gcip) : null,
): AuthSessionState {
  if (config.authMode === "disabled") {
    setAuthTokenProvider(null);
    return { status: "disabled" };
  }

  if (adapter === null) {
    setAuthTokenProvider(null);
    return { status: "missing_adapter", mode: "gcip" };
  }

  setAuthTokenProvider(() => adapter.getIdToken());
  return { status: "ready", mode: "gcip", adapter };
}
