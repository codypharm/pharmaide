import { useEffect, useState } from "react";
import { Award, History, Key, Mail, Settings, Shield } from "lucide-react";
import { getCurrentActor, type CurrentActorView } from "../api/auth";
import type { AuthSessionState } from "../auth/session";

type PharmacistProfilePageProps = {
  authSessionState?: AuthSessionState;
};

type ProfileAuthSummary = {
  avatarText: string;
  displayName: string;
  email: string;
  sessionTitle: string;
  sessionText: string;
  authModeLabel: string;
  workspaceLabel: string;
  verificationLabel: string;
  workspaceDetail: string;
};

export default function PharmacistProfilePage({
  authSessionState = { status: "disabled" },
}: PharmacistProfilePageProps) {
  const [serverActor, setServerActor] = useState<CurrentActorView | null>(null);
  const [verificationState, setVerificationState] = useState<
    "checking" | "verified" | "unavailable"
  >("checking");
  const profile = profileAuthSummary(authSessionState, serverActor);

  useEffect(() => {
    let active = true;
    setVerificationState("checking");
    setServerActor(null);

    getCurrentActor()
      .then((actor) => {
        if (!active) {
          return;
        }
        setServerActor(actor);
        setVerificationState("verified");
      })
      .catch(() => {
        if (!active) {
          return;
        }
        setServerActor(null);
        setVerificationState("unavailable");
      });

    return () => {
      active = false;
    };
  }, [authSessionState]);

  return (
    <div className="h-full overflow-y-auto p-8">
      <div className="mx-auto max-w-4xl space-y-8">
        <div className="flex items-center justify-between gap-6">
          <div className="flex items-center gap-6">
            <div className="flex h-24 w-24 items-center justify-center rounded-full border-4 border-white bg-slate-900 text-3xl font-bold text-white">
              {profile.avatarText}
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Pharmacist account
              </p>
              <h2 className="mt-1 text-3xl font-bold tracking-tight text-slate-900">
                {profile.displayName}
              </h2>
              <div className="mt-3 flex flex-wrap gap-3">
                <span className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-slate-500">
                  <Mail size={14} /> {profile.email}
                </span>
                <span className="rounded-md bg-slate-100 px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-600">
                  {profile.authModeLabel}
                </span>
                <span className={`rounded-md px-2 py-1 text-[10px] font-bold uppercase tracking-wider ${verificationClass(verificationState)}`}>
                  {verificationText(verificationState)}
                </span>
              </div>
            </div>
          </div>
          <button className="flex cursor-pointer items-center gap-2 rounded-xl border border-slate-200 bg-white px-6 py-2.5 font-bold text-slate-700 transition-colors hover:bg-slate-50">
            <Settings size={18} />
            Account Settings
          </button>
        </div>

        <div className="grid grid-cols-3 gap-6">
          <div className="col-span-2 space-y-6">
            <section className="rounded-2xl border border-slate-200 bg-white p-6">
              <h3 className="mb-4 flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-slate-500">
                <Award size={16} /> Professional Credentials
              </h3>
              <div className="grid grid-cols-2 gap-6">
                <ProfileField label="Role" value="Clinical Pharmacist" detail="Medication follow-up workspace" />
                <ProfileField label="Workspace" value={profile.workspaceLabel} detail={profile.workspaceDetail} />
                <ProfileField label="Session" value={profile.sessionTitle} detail="Browser session state" />
                <ProfileField label="Audit Trail" value="Enabled" detail="Pharmacist actions are attributable" />
              </div>
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-6">
              <h3 className="mb-4 flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-slate-500">
                <History size={16} /> Recent Activity
              </h3>
              <div className="space-y-4">
                {[
                  {
                    action: "Authentication status checked",
                    details: profile.verificationLabel,
                    time: "Now",
                  },
                  {
                    action: "Audit access ready",
                    details: "System audit entries are filtered by authenticated scope.",
                    time: "System",
                  },
                  {
                    action: "Privacy controls available",
                    details: "Use privacy mode in the dashboard header when working in shared spaces.",
                    time: "System",
                  },
                ].map((activity) => (
                  <div
                    key={activity.action}
                    className="flex items-center justify-between rounded-xl p-3 transition-colors hover:bg-slate-50"
                  >
                    <div>
                      <p className="text-sm font-bold text-slate-900">{activity.action}</p>
                      <p className="text-xs text-slate-500">{activity.details}</p>
                    </div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      {activity.time}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          </div>

          <div className="space-y-6">
            <section className="rounded-2xl border border-slate-200 bg-white p-6">
              <h3 className="mb-4 flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-slate-500">
                <Shield size={16} /> System Access
              </h3>
              <div className="space-y-4">
                <AccessRow label="Workspace scope" value={profile.workspaceLabel} tone="neutral" />
                <AccessRow label="Audit logs" value="Granted" tone="success" />
                <AccessRow label="Patient data" value="Scoped" tone="warning" />
                <AccessRow label="PHI storage" value="Server only" tone="neutral" />
              </div>
            </section>

            <section className="rounded-2xl bg-slate-900 p-6 text-white">
              <div className="mb-4 flex items-center gap-2">
                <Key size={18} className="text-[#A9A2F6]" />
                <h3 className="font-bold">{profile.sessionTitle}</h3>
              </div>
              <p className="mb-4 text-xs leading-6 text-slate-300">{profile.sessionText}</p>
              <p className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-200">
                {profile.workspaceDetail}
              </p>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}

function ProfileField({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div>
      <p className="mb-1 text-xs font-bold uppercase text-slate-400">{label}</p>
      <p className="text-sm font-bold text-slate-900">{value}</p>
      <p className="text-xs text-slate-500">{detail}</p>
    </div>
  );
}

function AccessRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "neutral" | "success" | "warning";
}) {
  const toneClass = {
    neutral: "bg-slate-100 text-slate-700",
    success: "bg-emerald-100 text-emerald-700",
    warning: "bg-amber-100 text-amber-700",
  }[tone];

  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm font-medium text-slate-600">{label}</span>
      <span className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase ${toneClass}`}>
        {value}
      </span>
    </div>
  );
}

function profileAuthSummary(
  authSessionState: AuthSessionState,
  serverActor: CurrentActorView | null,
): ProfileAuthSummary {
  if (serverActor) {
    const email = serverActor.email ?? "Email unavailable";
    return {
      avatarText: initialsForEmail(email),
      displayName: serverActor.email ?? "Verified pharmacist",
      email,
      sessionTitle:
        serverActor.auth_mode === "gcip" ? "GCIP session active" : "Local auth disabled",
      sessionText:
        "This identity was verified by the backend before showing scoped pharmacist access.",
      authModeLabel: serverActor.auth_mode === "gcip" ? "GCIP active" : "Local dev",
      workspaceLabel: serverActor.workspace_id ? "Workspace verified" : "Actor scoped",
      verificationLabel: "Server-verified identity",
      workspaceDetail: serverActor.workspace_id
        ? "Treatment and knowledge access use the authenticated workspace claim."
        : "Treatment and knowledge access use the verified actor scope.",
    };
  }

  if (authSessionState.status === "missing_adapter") {
    return {
      avatarText: "PA",
      displayName: "Sign-in setup required",
      email: "GCIP adapter missing",
      sessionTitle: "GCIP setup required",
      sessionText: "Browser auth is enabled, but the frontend sign-in adapter is not available.",
      authModeLabel: "GCIP setup",
      workspaceLabel: "Unavailable",
      verificationLabel: "Backend verification is unavailable.",
      workspaceDetail: "Workspace access cannot be verified until sign-in setup is complete.",
    };
  }

  if (authSessionState.status === "ready" && authSessionState.mode === "gcip") {
    const email = authSessionState.adapter.currentUserEmail?.() ?? "Not signed in";
    return {
      avatarText: initialsForEmail(email),
      displayName: email,
      email,
      sessionTitle: "GCIP session active",
      sessionText:
        "This browser session uses GCIP ID tokens. Tokens are kept in memory and sent as bearer auth on API requests.",
      authModeLabel: "GCIP active",
      workspaceLabel: "Claim scoped",
      verificationLabel: "Backend verification is still checking.",
      workspaceDetail: "Workspace access is controlled by authenticated claims.",
    };
  }

  return {
    avatarText: "PA",
    displayName: "Local pharmacist",
    email: "Local development session",
    sessionTitle: "Local auth disabled",
    sessionText:
      "This environment uses the development auth scaffold. Production should run with GCIP enabled.",
    authModeLabel: "Local dev",
    workspaceLabel: "Dev actor scoped",
    verificationLabel: "Backend verification is still checking.",
    workspaceDetail: "Workspace access is controlled by the development actor.",
  };
}

function verificationText(state: "checking" | "verified" | "unavailable"): string {
  if (state === "verified") {
    return "Server verified";
  }
  if (state === "unavailable") {
    return "Verification unavailable";
  }
  return "Verifying";
}

function verificationClass(state: "checking" | "verified" | "unavailable"): string {
  if (state === "verified") {
    return "bg-emerald-50 text-emerald-700";
  }
  if (state === "unavailable") {
    return "bg-amber-50 text-amber-700";
  }
  return "bg-slate-100 text-slate-600";
}

function initialsForEmail(email: string): string {
  if (!email.includes("@")) {
    return "PA";
  }

  return email.slice(0, 2).toUpperCase();
}
