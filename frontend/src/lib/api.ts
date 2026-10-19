import type {
  ActivityEvent,
  AdminOverview,
  AdminUser,
  AdminUserDetail,
  AuthUser,
  Detection,
  Health,
  ModelInfo,
  Paged,
  PredictResponse,
  Report,
  Stats,
} from "./types";

/** Empty in development (Vite proxies /api); the backend URL in production builds. */
export const API_BASE = ((import.meta.env.VITE_API_URL as string | undefined) ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  /** Machine-readable code from the backend, e.g. "not_calamansi_leaf", "invalid_credentials". */
  constructor(
    message: string,
    public status: number,
    public code?: string,
    public reason?: string,
    public extra: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function cookie(name: string): string | null {
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : null;
}

/** The backend requires the CSRF cookie value echoed in a header on every state-changing request. */
async function csrfToken(): Promise<string> {
  const existing = cookie("cl_csrf");
  if (existing) return existing;
  const res = await fetch(`${API_BASE}/api/auth/csrf`, { credentials: "same-origin" });
  return ((await res.json()) as { csrf_token: string }).csrf_token;
}

/** Called when the session can no longer be renewed (AuthProvider sends the user to the login page). */
let onSignedOut: (() => void) | null = null;
export function setSignedOutHandler(fn: (() => void) | null) {
  onSignedOut = fn;
}

const PREDICT_TIMEOUT_MS = 90_000;

async function send(path: string, init: RequestInit = {}): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (UNSAFE.has(method)) headers.set("X-CSRF-Token", await csrfToken());
  try {
    return await fetch(`${API_BASE}${path}`, { ...init, method, headers, credentials: "same-origin" });
  } catch (e) {
    if ((e as Error).name === "TimeoutError" || (e as Error).name === "AbortError")
      throw new ApiError("The server took too long to respond. Please try again; if it keeps happening, check that the backend is running.", 0, "timeout");
    throw new ApiError(
      "Cannot reach the server. If you just started the app, wait about 30 seconds while it loads and try again. Otherwise start it with start.bat and keep its window open.",
      0,
      "network",
    );
  }
}

let refreshing: Promise<boolean> | null = null;
function refreshSession(): Promise<boolean> {
  // One refresh at a time, even if several requests expire together.
  refreshing ??= send("/api/auth/refresh", { method: "POST" })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => setTimeout(() => (refreshing = null), 0));
  return refreshing;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res = await send(path, init);
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    // Access token expired: renew it once with the refresh cookie, then retry.
    if (await refreshSession()) res = await send(path, init);
    else onSignedOut?.();
  }
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    let code: string | undefined;
    let reason: string | undefined;
    let extra: Record<string, unknown> = {};
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
      else if (body.detail && typeof body.detail.message === "string") {
        ({ message, code, reason, ...extra } = body.detail);
      }
    } catch {
      if (res.status === 502 || res.status === 504) message = "Cannot reach the backend server (proxy error).";
    }
    throw new ApiError(message, res.status, code, reason, extra);
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

function qs(params: Record<string, string | number | undefined | null>): string {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : "";
}

export interface DetectionQuery {
  search?: string;
  predicted_class?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
  page_size?: number;
}

export const api = {
  health: () => request<Health>("/api/health"),
  stats: (days = 7) => request<Stats>(`/api/stats${qs({ days })}`),
  detections: (q: DetectionQuery = {}) => request<Paged<Detection>>(`/api/detections${qs({ ...q })}`),
  detection: (id: string) => request<Detection>(`/api/detections/${encodeURIComponent(id)}`),
  reports: (date_from?: string, date_to?: string) => request<Report>(`/api/reports${qs({ date_from, date_to })}`),
  model: () => request<ModelInfo>("/api/model"),
  predict: (file: Blob, filename: string) => {
    const form = new FormData();
    form.append("file", file, filename);
    // Classification normally takes 1-10 s on CPU; never leave the page waiting forever.
    return request<PredictResponse>("/api/predict", { method: "POST", body: form, signal: AbortSignal.timeout(PREDICT_TIMEOUT_MS) });
  },
  // ---- accounts
  me: () => request<{ user: AuthUser }>("/api/auth/me"),
  register: (b: { full_name: string; username: string; email: string; password: string }) =>
    request<{ message: string; email: string; resend_after: number }>("/api/auth/register", json(b)),
  verifyEmail: (email: string, code: string) =>
    request<{ message: string; user: AuthUser }>("/api/auth/verify-email", json({ email, code })),
  resendCode: (email: string) => request<{ message: string; resend_after: number }>("/api/auth/resend-code", json({ email })),
  login: (email: string, password: string) => request<{ user: AuthUser }>("/api/auth/login", json({ email, password })),
  logout: () => request<{ message: string }>("/api/auth/logout", { method: "POST" }),
  forgotPassword: (email: string) =>
    request<{ message: string; resend_after: number }>("/api/auth/forgot-password", json({ email })),
  resetPassword: (email: string, code: string, password: string) =>
    request<{ message: string }>("/api/auth/reset-password", json({ email, code, password })),
  changePassword: (current_password: string, new_password: string) =>
    request<{ message: string }>("/api/auth/change-password", json({ current_password, new_password })),
  // ---- administrators only (the server checks the role on every call)
  adminOverview: (days = 14) => request<AdminOverview>(`/api/admin/overview${qs({ days })}`),
  adminUsers: (q: { q?: string; status?: string; role?: string; verified?: string; page?: number; page_size?: number } = {}) =>
    request<Paged<AdminUser>>(`/api/admin/users${qs({ ...q })}`),
  adminUser: (id: string) => request<AdminUserDetail>(`/api/admin/users/${encodeURIComponent(id)}`),
  updateUser: (id: string, body: { full_name?: string; username?: string; account_status?: "active" | "suspended" }) =>
    request<{ message: string; user: AdminUser }>(`/api/admin/users/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteUser: (id: string) => request<{ message: string }>(`/api/admin/users/${encodeURIComponent(id)}`, { method: "DELETE" }),
  adminActivity: (q: { event_type?: string; status?: string; page?: number; page_size?: number } = {}) =>
    request<Paged<ActivityEvent>>(`/api/admin/activity${qs({ ...q })}`),
  exportUrl: (date_from?: string, date_to?: string, predicted_class?: string) =>
    `${API_BASE}/api/reports/export${qs({ date_from, date_to, predicted_class })}`,
};

/** Signed Supabase URLs are absolute; local-fallback URLs are relative to the API. */
export function imageSrc(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  return url.startsWith("/") ? `${API_BASE}${url}` : url;
}
