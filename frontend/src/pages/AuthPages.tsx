import { ArrowLeft, ArrowRight, AtSign, Check, CheckCircle2, KeyRound, Loader2, LogIn, Mail, MailCheck, RefreshCw, User, UserPlus } from "lucide-react";
import { useEffect, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import AuthShell, { Alert, CodeField, Field, PasswordChecklist, PasswordField } from "../components/AuthShell";
import ChangePasswordForm from "../components/ChangePasswordForm";
import { btn } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { homeFor, PASSWORD_RULES, safeNext, useAuth } from "../lib/auth";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/;

const submitCls =
  "group inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-forest-800 to-leaf-700 px-4 py-3.5 text-sm font-semibold text-white shadow-md shadow-forest-900/20 transition duration-200 ease-smooth hover:-translate-y-px hover:from-forest-700 hover:to-leaf-600 hover:shadow-lg hover:shadow-forest-900/25 active:translate-y-0 active:scale-[0.99] focus:outline-none focus-visible:ring-4 focus-visible:ring-lime-300/60 disabled:cursor-not-allowed disabled:opacity-75 disabled:hover:translate-y-0";

function Submit({ busy, busyLabel, done, doneLabel, children }: { busy: boolean; busyLabel?: string; done?: boolean; doneLabel?: string; children: ReactNode }) {
  // Disabled while the request runs (and after success), so the form cannot be submitted twice.
  return (
    <button type="submit" disabled={busy || done} aria-busy={busy} className={`${submitCls} ${done ? "!from-leaf-600 !to-leaf-500 !opacity-100" : ""}`}>
      {done ? (
        <span className="inline-flex animate-scale-in items-center gap-2"><CheckCircle2 size={17} /> {doneLabel}</span>
      ) : busy ? (
        <><Loader2 size={16} className="animate-spin" /> {busyLabel ?? children}</>
      ) : (
        children
      )}
    </button>
  );
}

/** "New here? Create an account" row under a form, with a quiet divider. */
function AltLink({ text, to, label }: { text: string; to: string; label: string }) {
  return (
    <p className="mt-6 short:mt-4 flex items-center gap-3 text-sm text-slate-600 before:h-px before:flex-1 before:bg-sage-200 after:h-px after:flex-1 after:bg-sage-200">
      <span>
        {text}{" "}
        <Link to={to} className="font-semibold text-leaf-700 underline-offset-4 transition hover:text-forest-800 hover:underline">{label}</Link>
      </span>
    </p>
  );
}

/** Seconds until another code may be requested; counts down once per second. */
function useCooldown(initial = 0) {
  const [left, setLeft] = useState(initial);
  useEffect(() => {
    if (left <= 0) return;
    const t = setTimeout(() => setLeft((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [left]);
  return [left, setLeft] as const;
}

function cooldownFrom(e: unknown): number {
  const v = (e as ApiError).extra?.retry_after;
  return typeof v === "number" ? v : 0;
}

// --------------------------------------------------------------------------- Login
export function Login() {
  const { signedIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});
  const [busy, setBusy] = useState(false);
  // Browsers do not autofill read-only fields: the form opens empty (e.g. right after signing out)
  // and unlocks on the first focus, where the browser can still offer saved accounts on request.
  const [locked, setLocked] = useState(true);
  const unlock = () => setLocked(false);
  const notice = (location.state as { message?: string } | null)?.message;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setError(null);
    const fe: { email?: string; password?: string } = {};
    if (!email.trim()) fe.email = "Enter your email address.";
    else if (!EMAIL_RE.test(email.trim())) fe.email = "This doesn't look like an email address.";
    if (!password) fe.password = "Enter your password.";
    setFieldErrors(fe);
    if (fe.email || fe.password) return;
    setBusy(true);
    try {
      const { user } = await api.login(email.trim(), password);
      signedIn(user);
      navigate(safeNext(params.get("next"), user), { replace: true });
    } catch (err) {
      const e2 = err as ApiError;
      if (e2.code === "email_not_verified")
        navigate(`/verify-email?email=${encodeURIComponent(email.trim())}`, {
          state: { notice: "Your email address is not verified yet. Enter the 6-digit code we emailed you, or request a new one." },
        });
      else setError(e2.message);
    } finally {
      setBusy(false);
      setPassword("");
    }
  };

  return (
    <AuthShell icon={LogIn} scene="login" title="Welcome back" subtitle="Sign in to check leaves and see your detection history.">
      {notice && <Alert kind="success">{notice}</Alert>}
      {error && <Alert>{error}</Alert>}
      <form onSubmit={submit} className="space-y-4 short:space-y-3" noValidate>
        <Field label="Email" icon={Mail} type="email" autoComplete="email" placeholder="you@example.com" value={email} error={fieldErrors.email}
          readOnly={locked} onFocus={unlock} onPointerDown={unlock}
          onChange={(e) => { setEmail(e.target.value); setFieldErrors((f) => ({ ...f, email: undefined })); }} />
        <PasswordField label="Password" autoComplete="current-password" value={password} error={fieldErrors.password}
          readOnly={locked} onFocus={unlock} onPointerDown={unlock}
          onChange={(e) => { setPassword(e.target.value); setFieldErrors((f) => ({ ...f, password: undefined })); }} />
        <div className="-mt-1 text-right text-sm">
          <Link to="/forgot-password" className="font-semibold text-leaf-700 underline-offset-4 transition hover:text-forest-800 hover:underline">Forgot password?</Link>
        </div>
        <Submit busy={busy} busyLabel="Signing in…"><LogIn size={16} /> Sign in <ArrowRight size={16} className="transition-transform duration-200 group-hover:translate-x-0.5" /></Submit>
      </form>
      <AltLink text="New to the system?" to="/register" label="Create an account" />
    </AuthShell>
  );
}

// --------------------------------------------------------------------------- Register
const REGISTER_STEPS = ["Your details", "Password", "Verify email"];

/** Progress indicator for the sign-up steps (the last one is the email-code page). */
function Steps({ current }: { current: number }) {
  return (
    <ol className="mb-6 flex items-center gap-2 short:mb-4" aria-label={`Step ${current + 1} of ${REGISTER_STEPS.length}`}>
      {REGISTER_STEPS.map((label, i) => {
        const done = i < current;
        const on = i === current;
        return (
          <li key={label} className="flex min-w-0 flex-1 flex-col gap-1.5" aria-current={on ? "step" : undefined}>
            <span className={`h-1.5 rounded-full transition-colors duration-300 ease-smooth ${done || on ? "bg-gradient-to-r from-leaf-600 to-matcha-500" : "bg-sage-200"}`} />
            <span className={`flex items-center gap-1 truncate text-xs tiny-phone:sr-only ${on ? "font-semibold text-forest-950" : done ? "text-leaf-700" : "text-slate-400"}`}>
              {done ? <Check size={12} className="shrink-0" /> : <span className="tabular-nums">{i + 1}.</span>}
              {label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function Register() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [f, setF] = useState({ full_name: "", username: "", email: "", password: "", confirm: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const set = (k: keyof typeof f) => (e: ChangeEvent<HTMLInputElement>) => {
    setF({ ...f, [k]: e.target.value });
    setErrors((x) => ({ ...x, [k]: "" }));
  };
  // Real-time check when leaving a field that already has a value.
  const check = (k: "full_name" | "username" | "email") => () => {
    if (f[k].trim()) setErrors((x) => ({ ...x, [k]: detailErrors()[k] ?? "" }));
  };

  const detailErrors = () => {
    const v: Record<string, string> = {};
    if (!f.full_name.trim()) v.full_name = "Enter your full name.";
    if (!/^[a-z0-9_]{3,30}$/.test(f.username.trim().toLowerCase())) v.username = "3–30 characters: letters, numbers or _.";
    if (!EMAIL_RE.test(f.email.trim())) v.email = "Enter a valid email address.";
    return v;
  };
  const passwordErrors = () => {
    const v: Record<string, string> = {};
    if (!PASSWORD_RULES.every((r) => r.test(f.password))) v.password = "The password does not meet all the requirements.";
    if (f.confirm !== f.password) v.confirm = "The passwords do not match.";
    return v;
  };

  const next = (e: FormEvent) => {
    e.preventDefault();
    const v = detailErrors();
    setErrors(v);
    if (Object.keys(v).length === 0) {
      setError(null);
      setStep(1);
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setError(null);
    const v = passwordErrors();
    setErrors(v);
    if (Object.keys(v).length) return;
    setBusy(true);
    try {
      const res = await api.register({
        full_name: f.full_name.trim(),
        username: f.username.trim().toLowerCase(),
        email: f.email.trim(),
        password: f.password,
      });
      setDone(true);
      setTimeout(() => navigate(`/verify-email?email=${encodeURIComponent(res.email)}`, { state: { message: res.message, cooldown: res.resend_after, fromRegister: true } }), 650);
    } catch (err) {
      const e2 = err as ApiError;
      // Problems with the details send the user back to step 1, next to the field concerned.
      if (e2.code === "email_taken") {
        setErrors({ email: e2.message });
        setStep(0);
      } else if (e2.code === "username_taken") {
        setErrors({ username: e2.message });
        setStep(0);
      } else if (e2.code === "weak_password") setErrors({ password: e2.message });
      else setError(e2.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell icon={UserPlus} scene="register" title="Create your account" subtitle="Check calamansi leaves for damage and keep a private history of every result.">
      <Steps current={step} />
      {error && <Alert>{error}</Alert>}
      {step === 0 ? (
        <form key="details" onSubmit={next} className="animate-fade-in space-y-4 short:space-y-3" noValidate>
          <Field label="Full name" icon={User} autoComplete="name" placeholder="Juan Dela Cruz" value={f.full_name} onChange={set("full_name")} onBlur={check("full_name")} error={errors.full_name} maxLength={100} autoFocus />
          <Field label="Username" icon={AtSign} autoComplete="username" placeholder="juan_dc" value={f.username} onChange={set("username")} onBlur={check("username")} error={errors.username} maxLength={30} hint="Lowercase letters, numbers and _" />
          <Field label="Email" icon={Mail} type="email" autoComplete="email" placeholder="you@example.com" value={f.email} onChange={set("email")} onBlur={check("email")} error={errors.email} />
          <button type="submit" className={submitCls}>
            Continue <ArrowRight size={16} className="transition-transform duration-200 group-hover:translate-x-0.5" />
          </button>
          <AltLink text="Already registered?" to="/login" label="Sign in" />
        </form>
      ) : (
        <form key="password" onSubmit={submit} className="animate-fade-in space-y-4 short:space-y-3" noValidate>
          <p className="rounded-xl bg-mint-50 px-3 py-2 text-xs text-slate-600 short:hidden">
            Creating <span className="font-semibold text-forest-950">@{f.username.trim().toLowerCase()}</span> for{" "}
            <span className="font-semibold text-forest-950">{f.email.trim()}</span>
          </p>
          <div>
            <PasswordField label="Password" autoComplete="new-password" value={f.password} onChange={set("password")} error={errors.password} autoFocus />
            <PasswordChecklist password={f.password} />
          </div>
          <PasswordField label="Confirm password" autoComplete="new-password" value={f.confirm} onChange={set("confirm")} error={errors.confirm}
            hint={f.confirm ? (f.confirm === f.password ? "Passwords match" : "Passwords do not match yet") : undefined} hintOk={f.confirm === f.password} />
          <div className="flex gap-3">
            <button type="button" onClick={() => { setError(null); setStep(0); }} disabled={busy || done} className={`${btn.secondary} py-3.5`}>
              <ArrowLeft size={16} /> Back
            </button>
            <div className="flex-1">
              <Submit busy={busy} busyLabel="Creating account…" done={done} doneLabel="Account created"><UserPlus size={16} /> Create account</Submit>
            </div>
          </div>
          <p className="text-xs text-slate-500 tiny:hidden">We will email you a 6-digit code to confirm your address.</p>
        </form>
      )}
    </AuthShell>
  );
}

// --------------------------------------------------------------------------- Verify e-mail
export function VerifyEmail() {
  const { signedIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const state = (location.state as { message?: string; notice?: string; cooldown?: number; fromRegister?: boolean } | null) ?? {};
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(state.message ?? null);
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useCooldown(state.cooldown ?? 0);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!EMAIL_RE.test(email.trim())) return setError("Enter the email address you registered with.");
    if (code.length !== 6) return setError("Enter the 6-digit code from the email.");
    setBusy(true);
    try {
      const res = await api.verifyEmail(email.trim(), code);
      signedIn(res.user);
      navigate(homeFor(res.user), { replace: true });
    } catch (err) {
      setError((err as ApiError).message);
      setCode("");
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    setError(null);
    if (!EMAIL_RE.test(email.trim())) return setError("Enter the email address you registered with.");
    try {
      const res = await api.resendCode(email.trim());
      setInfo(res.message);
      setCooldown(res.resend_after);
    } catch (err) {
      setError((err as ApiError).message);
      setCooldown(cooldownFrom(err));
    }
  };

  return (
    <AuthShell icon={MailCheck} scene={state.fromRegister ? "register" : "secure"} title="Verify your email" subtitle="Enter the 6-digit code we sent you. The code expires after a few minutes.">
      {state.fromRegister && <Steps current={2} />}
      {state.notice && <Alert kind="info">{state.notice}</Alert>}
      {info && <Alert kind="success">{info}</Alert>}
      {error && <Alert>{error}</Alert>}
      <form onSubmit={submit} className="space-y-4 short:space-y-3" noValidate>
        <Field label="Email" icon={Mail} type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <CodeField value={code} onChange={setCode} />
        <Submit busy={busy} busyLabel="Verifying…"><MailCheck size={16} /> Verify email</Submit>
      </form>
      <button onClick={resend} disabled={cooldown > 0} className={`${btn.secondary} mt-3 w-full`}>
        <RefreshCw size={15} /> {cooldown > 0 ? `Resend code in ${cooldown}s` : "Resend code"}
      </button>
      <p className="mt-4 text-center text-sm">
        <Link to="/login" className="font-semibold text-leaf-700 hover:underline">Back to sign in</Link>
      </p>
    </AuthShell>
  );
}

// --------------------------------------------------------------------------- Forgot password
export function ForgotPassword() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setError(null);
    if (!EMAIL_RE.test(email.trim())) return setError("Enter a valid email address.");
    setBusy(true);
    try {
      const res = await api.forgotPassword(email.trim());
      navigate(`/reset-password?email=${encodeURIComponent(email.trim())}`, { state: { message: res.message, cooldown: res.resend_after } });
    } catch (err) {
      setError((err as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell icon={KeyRound} scene="secure" title="Forgot your password?" subtitle="Enter the email of your account. If it is registered, we will send a 6-digit code to reset your password.">
      {error && <Alert>{error}</Alert>}
      <form onSubmit={submit} className="space-y-4 short:space-y-3" noValidate>
        <Field label="Email" icon={Mail} type="email" autoComplete="email" placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
        <Submit busy={busy} busyLabel="Sending code…">Send reset code <ArrowRight size={16} /></Submit>
      </form>
      <p className="mt-4 text-center text-sm">
        <Link to="/login" className="font-semibold text-leaf-700 hover:underline">Back to sign in</Link>
      </p>
    </AuthShell>
  );
}

// --------------------------------------------------------------------------- Reset password
export function ResetPassword() {
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const state = (location.state as { message?: string; cooldown?: number } | null) ?? {};
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(state.message ?? null);
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useCooldown(state.cooldown ?? 0);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!EMAIL_RE.test(email.trim())) return setError("Enter your account email.");
    if (code.length !== 6) return setError("Enter the 6-digit code from the email.");
    if (!PASSWORD_RULES.every((r) => r.test(password))) return setError("The new password does not meet all the requirements.");
    if (password !== confirm) return setError("The passwords do not match.");
    setBusy(true);
    try {
      const res = await api.resetPassword(email.trim(), code, password);
      navigate("/login", { replace: true, state: { message: res.message } });
    } catch (err) {
      setError((err as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    setError(null);
    try {
      const res = await api.forgotPassword(email.trim());
      setInfo(res.message);
      setCooldown(res.resend_after);
    } catch (err) {
      setError((err as ApiError).message);
      setCooldown(cooldownFrom(err));
    }
  };

  return (
    <AuthShell icon={KeyRound} scene="secure" title="Set a new password" subtitle="Enter the code from the email and choose a new password. All other sessions will be signed out.">
      {info && <Alert kind="success">{info}</Alert>}
      {error && <Alert>{error}</Alert>}
      <form onSubmit={submit} className="space-y-4 short:space-y-3" noValidate>
        <Field label="Email" icon={Mail} type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <CodeField value={code} onChange={setCode} />
        <div>
          <PasswordField label="New password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <PasswordChecklist password={password} />
        </div>
        <PasswordField label="Confirm new password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        <Submit busy={busy}>Change password</Submit>
      </form>
      <button onClick={resend} disabled={cooldown > 0 || !EMAIL_RE.test(email.trim())} className={`${btn.secondary} mt-3 w-full`}>
        <RefreshCw size={15} /> {cooldown > 0 ? `Send a new code in ${cooldown}s` : "Send a new code"}
      </button>
    </AuthShell>
  );
}

// --------------------------------------------------------------------------- Forced password change
/** Accounts created with a temporary password (create_admin.py) must choose a new one first. */
export function ChangePassword() {
  const { user, reload } = useAuth();
  const navigate = useNavigate();
  return (
    <AuthShell icon={KeyRound} scene="secure" title="Choose a new password" subtitle={<>You signed in with a temporary password{user ? <> as <strong>{user.email}</strong></> : null}. Set your own password to continue.</>}>
      <ChangePasswordForm
        onDone={async () => {
          await reload();
          navigate(homeFor(user), { replace: true });
        }}
      />
    </AuthShell>
  );
}
