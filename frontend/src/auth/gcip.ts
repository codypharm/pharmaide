import { getApp, getApps, initializeApp, type FirebaseApp } from "firebase/app";
import {
  getAuth,
  signInWithEmailAndPassword,
  signOut as firebaseSignOut,
  type Auth,
} from "firebase/auth";

import type { AuthTokenAdapter } from "./session";
import type { FrontendConfig } from "../config";

const APP_NAME = "pharmaide";

export type GcipAuthAdapter = AuthTokenAdapter & {
  signInWithEmailPassword: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  currentUserEmail: () => string | null;
};

export function createGcipAuthAdapter(
  config: NonNullable<FrontendConfig["gcip"]>,
): GcipAuthAdapter {
  const auth = getAuth(firebaseApp(config));
  return authAdapter(auth);
}

function authAdapter(auth: Auth): GcipAuthAdapter {
  return {
    getIdToken: async () => auth.currentUser?.getIdToken() ?? null,
    signInWithEmailPassword: async (email: string, password: string) => {
      await signInWithEmailAndPassword(auth, email, password);
    },
    signOut: async () => {
      await firebaseSignOut(auth);
    },
    currentUserEmail: () => auth.currentUser?.email ?? null,
  };
}

function firebaseApp(config: NonNullable<FrontendConfig["gcip"]>): FirebaseApp {
  if (getApps().some((app) => app.name === APP_NAME)) {
    return getApp(APP_NAME);
  }

  return initializeApp(
    {
      apiKey: config.apiKey,
      authDomain: config.authDomain,
      projectId: config.projectId,
    },
    APP_NAME,
  );
}
