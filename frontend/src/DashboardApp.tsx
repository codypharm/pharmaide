import { Activity, Bell, ClipboardList, FileText, Flame, Map, Search, ShieldCheck, Plus, ChevronRight, LogOut } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { Outlet, NavLink, Link } from "react-router-dom";
import { UnauthorizedError, setUnauthorizedHandler } from "./api/client";
import type { AuthSessionState, AuthTokenAdapter } from "./auth/session";

type DashboardAppProps = {
  authSessionState?: AuthSessionState;
};

function DashboardApp({
  authSessionState = { status: "disabled" },
}: DashboardAppProps) {
  const [isPrivacyMode, setIsPrivacyMode] = useState(false);
  const [authError, setAuthError] = useState<UnauthorizedError | null>(null);
  const [signedInEmail, setSignedInEmail] = useState(() => currentSessionEmail(authSessionState));
  const [isSigningOut, setIsSigningOut] = useState(false);
  const hasMissingAuthAdapter = authSessionState.status === "missing_adapter";
  const interactiveGcipAdapter = authSessionState.status === "ready"
    && authSessionState.mode === "gcip"
    && hasInteractiveGcipAuth(authSessionState.adapter)
    ? authSessionState.adapter
    : null;
  const needsGcipSignIn = interactiveGcipAdapter !== null && signedInEmail === null;

  useEffect(() => {
    setUnauthorizedHandler((error) => {
      setAuthError(error);
      if (interactiveGcipAdapter !== null) {
        setSignedInEmail(null);
        void interactiveGcipAdapter.signOut?.().catch(() => undefined);
      }
    });
    return () => setUnauthorizedHandler(null);
  }, [interactiveGcipAdapter]);

  useEffect(() => {
    setSignedInEmail(currentSessionEmail(authSessionState));
  }, [authSessionState]);

  async function handleSignOut() {
    if (typeof interactiveGcipAdapter?.signOut !== "function") {
      return;
    }

    setIsSigningOut(true);
    try {
      await interactiveGcipAdapter.signOut();
      setAuthError(null);
      setSignedInEmail(null);
    } finally {
      setIsSigningOut(false);
    }
  }

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50 font-sans text-slate-900">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-slate-200 flex flex-col z-40">
        <div className="p-8 pb-4">
          <Link to="/" className="flex items-center gap-2 group cursor-pointer">
            <div className="w-9 h-9 bg-[#5548E8] rounded-xl flex items-center justify-center text-white shadow-sm group-hover:bg-[#463AD4] transition-colors">
              <ShieldCheck size={20} />
            </div>
            <h1 className="text-xl font-bold tracking-tighter text-slate-900 group-hover:text-[#5548E8] transition-colors">PharmaAide</h1>
          </Link>
        </div>

        <nav className="flex flex-col gap-0.5 px-3 flex-1 mt-6">
          <NavLink
            to="/dashboard/triage"
            className={({ isActive }) => 
              `flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${
                isActive 
                  ? "bg-slate-100 text-slate-900" 
                  : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            <Flame size={18} />
            Triage Queue
          </NavLink>
          <NavLink
            to="/dashboard/surveillance"
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${
                isActive
                  ? "bg-slate-100 text-slate-900"
                  : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            <Activity size={18} />
            Surveillance
          </NavLink>
          <NavLink
            to="/dashboard/ingestions"
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${
                isActive
                  ? "bg-slate-100 text-slate-900"
                  : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            <ClipboardList size={18} />
            Treatments
          </NavLink>
          <NavLink
            to="/dashboard/heatmaps"
            className={({ isActive }) => 
              `flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${
                isActive 
                  ? "bg-slate-100 text-slate-900" 
                  : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            <Map size={18} />
            Adherence
          </NavLink>
          
          <div className="h-px bg-slate-100 my-4 mx-4" />

          <NavLink
            to="/dashboard/knowledge"
            className={({ isActive }) => 
              `flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${
                isActive 
                  ? "bg-slate-100 text-slate-900" 
                  : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            <FileText size={18} />
            Clinical Assets
          </NavLink>
          <NavLink
            to="/dashboard/audits"
            className={({ isActive }) => 
              `flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${
                isActive 
                  ? "bg-slate-100 text-slate-900" 
                  : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            <ShieldCheck size={18} />
            System Audit
          </NavLink>

          <div className="mt-8 px-4">
            <Link 
              to="/dashboard/new-treatment"
              className="w-full bg-[#5548E8] hover:bg-[#463AD4] !text-white py-2.5 rounded-xl flex items-center justify-center gap-2 text-sm font-bold transition-all shadow-sm shadow-[#D9D5FB]"
            >
              <Plus size={18} />
              New Treatment
            </Link>
          </div>
        </nav>

        <Link to="/dashboard/profile" className="p-4 m-4 bg-slate-50 rounded-2xl flex items-center gap-3 hover:bg-slate-100 transition-all cursor-pointer border border-slate-100">
          <div className="w-10 h-10 rounded-xl bg-white border border-slate-200 flex items-center justify-center font-bold text-slate-700 shadow-sm">PP</div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-bold text-slate-900 truncate">Dr. E. Thorne</p>
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Pharmacist</p>
          </div>
          <ChevronRight size={14} className="text-slate-300" />
        </Link>
      </aside>

      {/* Workspace */}
      <main className="flex-1 flex flex-col min-w-0 bg-slate-50/50">
        <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-8 z-30 shadow-sm shadow-slate-100/50">
          <div className="relative w-80">
            <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input 
              placeholder="Search Directory..." 
              type="text" 
              className="w-full pl-10 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[#D9D5FB] focus:border-[#5548E8] transition-all"
            />
          </div>

          <div className="flex items-center gap-6">
            <label className="flex items-center gap-3 cursor-pointer group">
              <span className="text-sm font-semibold text-slate-600 group-hover:text-slate-900 transition-colors">Privacy Mode</span>
              <div className="relative inline-flex items-center cursor-pointer">
                <input 
                  type="checkbox" 
                  value="" 
                  className="sr-only peer" 
                  checked={isPrivacyMode}
                  onChange={(e) => setIsPrivacyMode(e.target.checked)}
                />
                <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[#5548E8]"></div>
              </div>
            </label>
            <button className="w-10 h-10 rounded-full hover:bg-slate-100 text-slate-500 flex items-center justify-center relative transition-colors">
              <Bell size={20} />
              <span className="absolute top-2.5 right-2.5 w-2 h-2 bg-red-500 rounded-full border-2 border-white"></span>
            </button>
            <div className="pl-6 border-l border-slate-200 flex items-center gap-3">
              <span className="max-w-48 truncate text-sm font-semibold text-slate-700">
                {signedInEmail ?? "Thomas F."}
              </span>
              <div className="w-8 h-8 bg-yellow-100 text-yellow-800 rounded-full flex items-center justify-center font-bold text-xs">
                {initialsForUser(signedInEmail)}
              </div>
              {signedInEmail && typeof interactiveGcipAdapter?.signOut === "function" ? (
                <button
                  aria-label="Sign out"
                  className="rounded-lg border border-slate-200 p-2 text-slate-500 transition-colors hover:border-slate-300 hover:bg-slate-100 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={isSigningOut}
                  onClick={handleSignOut}
                  type="button"
                >
                  <LogOut size={16} />
                </button>
              ) : null}
            </div>
          </div>
        </header>

        {authError && (
          <div
            role="alert"
            className="border-b border-amber-200 bg-amber-50 px-8 py-3 text-sm text-slate-800"
          >
            <span className="font-bold">Session needs attention.</span>{" "}
            Sign in again to continue.
            {authError.requestId ? (
              <span className="ml-2 text-slate-500">Reference ID: {authError.requestId}</span>
            ) : null}
          </div>
        )}

        <div className="flex-1 overflow-hidden">
          {hasMissingAuthAdapter ? (
            <MissingAuthAdapterPanel />
          ) : needsGcipSignIn ? (
            <GcipSignInPanel
              adapter={interactiveGcipAdapter}
              onSignedIn={(email) => {
                setAuthError(null);
                setSignedInEmail(email);
              }}
            />
          ) : (
            <Outlet context={{ isPrivacyMode }} />
          )}
        </div>
      </main>
    </div>
  );
}

function hasInteractiveGcipAuth(adapter: AuthTokenAdapter): adapter is AuthTokenAdapter & {
  signInWithEmailPassword: (email: string, password: string) => Promise<void>;
} {
  return typeof adapter.signInWithEmailPassword === "function";
}

function currentSessionEmail(authSessionState: AuthSessionState): string | null {
  if (authSessionState.status !== "ready") {
    return null;
  }

  return authSessionState.adapter.currentUserEmail?.() ?? null;
}

function initialsForUser(email: string | null): string {
  if (!email) {
    return "TF";
  }

  return email.slice(0, 2).toUpperCase();
}

function GcipSignInPanel({
  adapter,
  onSignedIn,
}: {
  adapter: AuthTokenAdapter & {
    signInWithEmailPassword: (email: string, password: string) => Promise<void>;
  };
  onSignedIn: (email: string | null) => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSigningIn(true);
    setErrorMessage(null);

    try {
      await adapter.signInWithEmailPassword(email.trim(), password);
      onSignedIn(adapter.currentUserEmail?.() ?? email.trim());
    } catch {
      setErrorMessage("Sign-in failed. Check the email and password, then try again.");
    } finally {
      setIsSigningIn(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto p-8">
      <section className="mx-auto max-w-md rounded-xl border border-slate-200 bg-white p-6 text-slate-900">
        <p className="text-xs font-bold uppercase tracking-wider text-[#5548E8]">
          Secure access
        </p>
        <h2 className="mt-2 text-xl font-bold">Sign in to PharmaAide</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Use your pharmacist account to access patient workflows.
        </p>

        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          <label className="block">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Email
            </span>
            <input
              autoComplete="email"
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none transition-colors focus:border-[#5548E8] focus:ring-2 focus:ring-[#D9D5FB]"
              name="email"
              onChange={(event) => setEmail(event.target.value)}
              required
              type="email"
              value={email}
            />
          </label>

          <label className="block">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Password
            </span>
            <input
              autoComplete="current-password"
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none transition-colors focus:border-[#5548E8] focus:ring-2 focus:ring-[#D9D5FB]"
              name="password"
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
          </label>

          {errorMessage ? (
            <div
              className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-slate-800"
              role="alert"
            >
              {errorMessage}
            </div>
          ) : null}

          <button
            className="w-full rounded-lg bg-[#5548E8] px-4 py-2.5 text-sm font-bold text-white transition-colors hover:bg-[#463AD4] disabled:cursor-not-allowed disabled:bg-slate-300"
            disabled={isSigningIn}
            type="submit"
          >
            {isSigningIn ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </section>
    </div>
  );
}

function MissingAuthAdapterPanel() {
  return (
    <div className="h-full overflow-y-auto p-8">
      <section
        role="alert"
        className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-slate-900"
      >
        <p className="text-xs font-bold uppercase tracking-wider text-amber-700">
          Sign-in setup required
        </p>
        <h2 className="mt-2 text-xl font-bold">GCIP sign-in is not connected.</h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-700">
          Browser auth is set to GCIP, but the frontend sign-in adapter is not wired yet.
          Complete the GCIP adapter before using protected dashboard workflows.
        </p>
      </section>
    </div>
  );
}

export default DashboardApp;
