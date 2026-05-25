import { getJson } from "./client";

export type CurrentActorView = {
  actor_id: string;
  subject: string;
  auth_mode: "disabled" | "gcip";
  email: string | null;
  workspace_id: string | null;
  kb_scope_id: string;
};

export function getCurrentActor(): Promise<CurrentActorView> {
  return getJson<CurrentActorView>("/auth/me");
}
