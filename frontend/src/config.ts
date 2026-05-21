export type FrontendAuthMode = "disabled" | "gcip";

export type FrontendConfig = {
  apiBaseUrl: string;
  authMode: FrontendAuthMode;
  gcip: {
    apiKey: string;
    authDomain: string;
    projectId: string;
  } | null;
};

type FrontendEnv = {
  VITE_API_BASE_URL?: string;
  VITE_AUTH_MODE?: string;
  VITE_GCIP_API_KEY?: string;
  VITE_GCIP_AUTH_DOMAIN?: string;
  VITE_GCIP_PROJECT_ID?: string;
};

const DEFAULT_API_BASE_URL = "http://localhost:8000";

export function getFrontendConfig(env: FrontendEnv = import.meta.env as FrontendEnv): FrontendConfig {
  const authMode = parseAuthMode(env.VITE_AUTH_MODE);
  return {
    apiBaseUrl: clean(env.VITE_API_BASE_URL) ?? DEFAULT_API_BASE_URL,
    authMode,
    gcip: authMode === "gcip" ? requiredGcipConfig(env) : null,
  };
}

function parseAuthMode(value: string | undefined): FrontendAuthMode {
  const normalized = clean(value) ?? "disabled";
  if (normalized === "disabled" || normalized === "gcip") {
    return normalized;
  }
  throw new Error(`Unsupported frontend auth mode: ${normalized}`);
}

function requiredGcipConfig(env: FrontendEnv): NonNullable<FrontendConfig["gcip"]> {
  const apiKey = clean(env.VITE_GCIP_API_KEY);
  const authDomain = clean(env.VITE_GCIP_AUTH_DOMAIN);
  const projectId = clean(env.VITE_GCIP_PROJECT_ID);
  if (!apiKey || !authDomain || !projectId) {
    throw new Error(
      "GCIP auth requires VITE_GCIP_API_KEY, VITE_GCIP_AUTH_DOMAIN, and VITE_GCIP_PROJECT_ID",
    );
  }
  return { apiKey, authDomain, projectId };
}

function clean(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}
