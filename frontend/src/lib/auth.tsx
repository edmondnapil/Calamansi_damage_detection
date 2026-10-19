import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Spinner } from "../components/ui";
import { api, ApiError, setSignedOutHandler } from "./api";
import type { AuthUser } from "./types";

type Status = "loading" | "signed_out" | "unverified" | "suspended" | "signed_in";

interface AuthState {
  status: Status;
  user: AuthUser | null;
  /** E-mail of a signed-in but unverified account (for the verification page). */
  pendingEmail: string | null;
  reload: () => Promise<void>;
  signedIn: (user: AuthUser) => void;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

/** Session state comes from the server (/api/auth/me): cookies are HttpOnly, the page cannot read them. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [pendingEmail, setPendingEmail] = useState<string | null>(null);
  const navigate = useNavigate();

  const reload = useCallback(async () => {
    try {
      const { user } = await api.me();
      setUser(user);
      setStatus("signed_in");
    } catch (e) {
      setUser(null);
      const err = e as ApiError;
      if (err.code === "email_not_verified") {
        setPendingEmail(String(err.extra.email ?? ""));
        setStatus("unverified");
      } else if (err.code === "account_suspended") setStatus("suspended");
      else setStatus("signed_out");
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    // A protected request found the session expired and it could not be renewed.
    setSignedOutHandler(() => {
      setUser(null);
      setStatus("signed_out");
    });
    return () => setSignedOutHandler(null);
  }, []);

  const signedIn = useCallback((u: AuthUser) => {
    setUser(u);
    setStatus("signed_in");
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
      setStatus("signed_out");
      navigate("/login", { replace: true, state: { message: "You have been signed out." } });
    }
  }, [navigate]);

  const value = useMemo(
    () => ({ status, user, pendingEmail, reload, signedIn, signOut }),
    [status, user, pendingEmail, reload, signedIn, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/** Dashboard a signed-in account belongs on: administrators get the admin dashboard. */
export function homeFor(user: AuthUser | null): string {
  return user?.role === "admin" ? "/admin" : "/app";
}

/** Wraps every /app and /admin page. The server enforces the same rules on every API call. */
export function RequireAuth() {
  const { status, pendingEmail, user } = useAuth();
  const location = useLocation();
  if (status === "loading") return <Spinner label="Checking your session…" />;
  if (status === "signed_in" && user?.must_change_password)
    return <Navigate to="/change-password" replace />;
  if (status === "unverified")
    return <Navigate to={`/verify-email?email=${encodeURIComponent(pendingEmail ?? "")}`} replace />;
  if (status === "suspended") return <Navigate to="/login" replace state={{ message: "This account has been suspended." }} />;
  if (status === "signed_out")
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  return <Outlet />;
}

/** Signed-in accounts only (used by the forced password-change page). */
export function RequireSignedIn() {
  const { status } = useAuth();
  if (status === "loading") return <Spinner label="Checking your session…" />;
  if (status !== "signed_in") return <Navigate to="/login" replace />;
  return <Outlet />;
}

/** Admin pages. Ordinary users who type an /admin URL are sent to their own dashboard;
 * the admin API refuses them independently (403). */
export function RequireAdmin() {
  const { user } = useAuth();
  return user?.role === "admin" ? <Outlet /> : <Navigate to="/app" replace />;
}

/** Login/register pages: already signed-in users go straight to their dashboard. */
export function PublicOnly() {
  const { status, user } = useAuth();
  if (status === "loading") return <Spinner label="Loading…" />;
  if (status === "signed_in") return <Navigate to={homeFor(user)} replace />;
  return <Outlet />;
}

export const PASSWORD_RULES: { label: string; test: (p: string) => boolean }[] = [
  { label: "8–72 characters", test: (p) => p.length >= 8 && p.length <= 72 },
  { label: "a lowercase letter", test: (p) => /[a-z]/.test(p) },
  { label: "an uppercase letter", test: (p) => /[A-Z]/.test(p) },
  { label: "a number", test: (p) => /\d/.test(p) },
  { label: "a symbol", test: (p) => /[^A-Za-z0-9]/.test(p) },
];

/** Where to go after signing in: the page originally asked for (if this role may open it), else the home dashboard. */
export function safeNext(next: string | null, user: AuthUser | null): string {
  if (user?.must_change_password) return "/change-password";
  const allowed = next && !next.startsWith("//") && (next.startsWith("/app") || (next.startsWith("/admin") && user?.role === "admin"));
  return allowed ? next : homeFor(user);
}
