import { AlertTriangle, ArrowLeft, CheckCircle2, Eye, EyeOff, Info, Leaf, Lock, ScanLine, ShieldCheck, Sparkles, type LucideIcon } from "lucide-react";
import { useEffect, useId, useState, type InputHTMLAttributes, type KeyboardEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import fieldPhoto from "../assets/landing/how-calamansi-field.webp";
import heroPhoto from "../assets/landing/hero-calamansi-leaves.webp";
import treePhoto from "../assets/landing/about-calamansi-tree.webp";
import { api } from "../lib/api";
import { pct } from "../lib/format";
import { PASSWORD_RULES } from "../lib/auth";
import { LeafLogo } from "./ui";

const inputBase =
  "peer w-full rounded-xl border bg-cream-50 py-3 short:py-2.5 text-sm text-forest-950 placeholder:text-slate-400 transition duration-200 ease-smooth focus:bg-white focus:outline-none focus:ring-4";
const inputOk = "border-sage-200 hover:border-sage-400 focus:border-leaf-500 focus:ring-lime-300/40";
const inputBad = "border-red-300 bg-red-50/40 focus:border-red-400 focus:ring-red-100";
const iconCls = "pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-sage-400 transition-colors duration-200 peer-focus:text-leaf-600";

/** Photo and wording of the visual panel; every photo is licensed (see assets/landing/credits.json). */
const SCENES = {
  login: {
    photo: heroPhoto,
    alt: "Calamansi leaves and a young green fruit on a tree in Nueva Ecija, Philippines",
    credit: "Photo: Judgefloro, Wikimedia Commons, CC BY-SA 4.0",
    eyebrow: "Calamansi plant-health assistant",
    heading: "Spot leaf damage early. Keep every tree productive.",
    text: "Photograph a calamansi leaf and get a Healthy or Damaged result with a confidence score in seconds.",
  },
  register: {
    photo: fieldPhoto,
    alt: "Calamansi fruit and leaves in a calamansi field in Nueva Ecija, Philippines",
    credit: "Photo: Judgefloro, Wikimedia Commons, CC BY-SA 4.0",
    eyebrow: "Create a free account",
    heading: "Your own record of calamansi leaf health.",
    text: "Every leaf you check is saved to your private history, so you can follow your trees over time and export reports.",
  },
  secure: {
    photo: treePhoto,
    alt: "A calamansi tree in the Philippines",
    credit: "Photo: Iiping, Wikimedia Commons, public domain",
    eyebrow: "Account security",
    heading: "Your account is protected at every step.",
    text: "Email codes confirm that it is really you. Codes expire quickly and are never shown to anyone else.",
  },
} as const;
export type AuthScene = keyof typeof SCENES;

const FEATURES: [LucideIcon, string, string][] = [
  [ScanLine, "Instant classification", "Healthy or Damaged, with the model's confidence"],
  [ShieldCheck, "Calamansi leaves only", "Photos of anything else are rejected, not guessed"],
  [Lock, "Private history", "Your detections are visible to you alone"],
];

/** Real offline test results of the deployed model (public /api/model); hidden if unavailable. */
function ModelFacts() {
  const [facts, setFacts] = useState<[string, string][] | null>(null);
  useEffect(() => {
    let live = true;
    api
      .model()
      .then((m) => {
        const ev = m.evaluation?.test;
        const acc = m.leaf_check?.calamansi_test_acceptance?.all_photos;
        if (!live || !ev) return;
        setFacts([
          [pct(ev.accuracy), "test accuracy"],
          [String(ev.n), "independent test photos"],
          ...(acc != null ? ([[pct(acc), "calamansi photos recognised"]] as [string, string][]) : []),
        ]);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
  if (!facts) return null;
  return (
    <dl className="mt-8 short:mt-6 short:pt-4 grid animate-fade-in grid-cols-3 [&>div]:flex [&>div]:flex-col-reverse [&>div]:justify-end gap-3 border-t border-white/15 pt-6">
      {facts.map(([v, k]) => (
        <div key={k} className="min-w-0">
          <dt className="mt-0.5 text-xs leading-snug text-white/70">{k}</dt>
          <dd className="text-2xl font-bold tracking-tight text-lime-300">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Soft botanical outline used as a quiet decoration behind the form. */
function LeafOutline({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 200" fill="none" aria-hidden="true" className={className}>
      <path d="M60 6C22 46 10 98 22 142c8 30 24 46 38 52 14-6 30-22 38-52C110 98 98 46 60 6Z" stroke="currentColor" strokeWidth="2.2" />
      <path d="M60 22v172M60 64l-20-16M60 92 34 72M60 120 30 98M60 148l-24-20M60 64l20-16M60 92l26-20M60 120l30-22M60 148l24-20" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

/** Shared layout of the sign-in, registration, verification and recovery pages. */
export default function AuthShell({
  title,
  subtitle,
  icon: Icon = Lock,
  scene = "login",
  children,
}: {
  title: string;
  subtitle?: ReactNode;
  icon?: LucideIcon;
  scene?: AuthScene;
  children: ReactNode;
}) {
  const s = SCENES[scene];
  return (
    <div className="grid h-dvh overflow-hidden bg-cream-50 font-sans text-forest-950 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1fr)]">
      {/* ---- visual panel (desktop) */}
      <aside className="relative hidden overflow-hidden bg-forest-950 lg:block">
        <img src={s.photo} alt={s.alt} className="absolute inset-0 h-full w-full object-cover opacity-90" />
        <div className="absolute inset-0 bg-gradient-to-br from-forest-950/80 via-forest-900/55 to-forest-950/95" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_left,rgba(190,220,75,0.18),transparent_55%)]" />
        <div className="relative flex h-full flex-col p-10 text-white xl:p-12 short:p-8">
          <Link to="/" className="flex w-fit items-center gap-3 rounded-xl">
            <LeafLogo size={42} />
            <span>
              <span className="block text-[17px] font-bold leading-tight">Calamansi Leaf Detection</span>
              <span className="block text-xs text-white/65">Image-based plant-health check</span>
            </span>
          </Link>
          <div className="my-auto max-w-lg animate-fade-up py-8 short:py-4">
            <span className="inline-flex items-center gap-2 rounded-full bg-lime-400/15 px-3 py-1 text-xs font-semibold text-lime-300 ring-1 ring-lime-300/30">
              <Leaf size={13} /> {s.eyebrow}
            </span>
            <h2 className="mt-5 text-[34px] font-bold leading-[1.15] tracking-tight xl:text-[40px] short:mt-4 short:text-[30px] short:xl:text-[32px]">{s.heading}</h2>
            <p className="mt-4 max-w-md text-[15px] leading-relaxed text-white/80">{s.text}</p>
            <ul className="mt-8 space-y-3.5 short:mt-6 short:space-y-2.5 tiny:hidden">
              {FEATURES.map(([I, t, d]) => (
                <li key={t} className="flex items-start gap-3.5">
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-forest-800/80 text-lime-300 ring-1 ring-white/10">
                    <I size={18} />
                  </span>
                  <span className="pt-0.5">
                    <span className="block text-sm font-semibold">{t}</span>
                    <span className="block text-[13px] text-white/65 short:hidden">{d}</span>
                  </span>
                </li>
              ))}
            </ul>
            <ModelFacts />
          </div>
          <p className="text-[11px] text-white/50">{s.credit}</p>
        </div>
      </aside>

      {/* ---- form side */}
      <div className="relative flex min-h-0 min-w-0 flex-col overflow-y-auto overflow-x-hidden">
        {/* clipped decoration layer: the leaves must never make the page scroll */}
        <div className="pointer-events-none absolute inset-0 hidden overflow-hidden lg:block" aria-hidden="true">
          <LeafOutline className="absolute -right-12 top-24 h-64 w-40 rotate-[28deg] text-sage-200" />
          <LeafOutline className="absolute -bottom-14 -left-6 h-72 w-44 -rotate-[24deg] text-sage-200/80" />
        </div>

        {/* compact photo banner (phones and tablets) */}
        <div className="relative h-28 shrink-0 overflow-hidden bg-forest-950 sm:h-40 short:h-24 tiny:h-[76px] lg:hidden">
          <img src={s.photo} alt="" className="absolute inset-0 h-full w-full object-cover opacity-90" />
          <div className="absolute inset-0 bg-gradient-to-b from-forest-950/75 via-forest-900/50 to-forest-950/85" />
          <div className="relative flex h-full flex-col px-4 pb-10 pt-4 text-white sm:px-8 tiny:pt-3">
            <div className="flex items-center justify-between">
              <Link to="/" className="flex items-center gap-2.5 rounded-xl">
                <LeafLogo size={36} />
                <span className="text-[15px] font-bold leading-tight">Calamansi Leaf Detection</span>
              </Link>
              <Link to="/" className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm font-medium text-white/85 transition hover:bg-white/10">
                <ArrowLeft size={15} /> Home
              </Link>
            </div>
            <p className="mt-auto hidden max-w-sm text-lg font-semibold leading-snug sm:block short:hidden">{s.heading}</p>
          </div>
        </div>

        <div className="absolute right-6 top-5 z-10 hidden lg:block">
          <Link to="/" className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-sm font-medium text-sage-600 transition hover:bg-sage-100 hover:text-forest-900">
            <ArrowLeft size={15} /> Back to home
          </Link>
        </div>

        <div className="relative mx-auto -mt-7 flex w-full max-w-[460px] flex-1 flex-col justify-start px-4 pb-4 sm:px-0 lg:mt-0 lg:justify-center lg:py-6 short:lg:py-3">
          <div className="animate-fade-up overflow-hidden rounded-3xl border border-sage-200/70 bg-white shadow-lift">
            <div className="h-1.5 bg-gradient-to-r from-forest-700 via-leaf-500 to-lime-400" />
            <div className="p-5 sm:p-8 short:sm:px-7 short:sm:py-6 tiny:p-4">
              {/* icon beside the title: one line less than stacking them */}
              <div className="flex items-center gap-3.5">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-leaf-500 to-forest-700 text-white shadow-md shadow-leaf-600/25">
                  <Icon size={21} />
                </span>
                <h1 className="text-[24px] font-bold leading-tight tracking-tight sm:text-[27px]">{title}</h1>
              </div>
              {subtitle && <p className="mt-3 text-sm leading-relaxed text-slate-600 short-phone:hidden">{subtitle}</p>}
              <div className="mt-6 short:mt-5 tiny:mt-4">{children}</div>
            </div>
          </div>
          <p className="mt-5 hidden lg:flex short:!hidden items-center justify-center gap-1.5 text-center text-xs text-sage-600">
            <Sparkles size={13} className="text-matcha-500" /> Web-Based Calamansi Leaf Damage Detection Using Image Classification
          </p>
        </div>
      </div>
    </div>
  );
}

type FieldProps = InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string; hint?: ReactNode; icon?: LucideIcon };

export function Field({ label, error, hint, icon: Icon, id, ...props }: FieldProps) {
  const auto = useId();
  const fid = id ?? auto;
  const msgId = `${fid}-msg`;
  return (
    <div>
      <label htmlFor={fid} className="text-sm font-semibold text-forest-950">{label}</label>
      <div className="relative mt-1.5">
        <input
          id={fid}
          {...props}
          aria-invalid={!!error}
          aria-describedby={error || hint ? msgId : undefined}
          className={`${inputBase} ${Icon ? "pl-10" : "pl-3.5"} pr-3.5 ${error ? inputBad : inputOk}`}
        />
        {Icon && <Icon size={17} className={iconCls} />}
      </div>
      {error ? (
        <p id={msgId} className="mt-1.5 flex animate-slide-down items-center gap-1 text-xs text-red-700">
          <AlertTriangle size={12} className="shrink-0" /> {error}
        </p>
      ) : (
        hint && <p id={msgId} className="mt-1.5 text-xs text-slate-500 short-phone:sr-only">{hint}</p>
      )}
    </div>
  );
}

export function PasswordField({
  label,
  error,
  hint,
  hintOk,
  id,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string; hint?: string; hintOk?: boolean }) {
  const [show, setShow] = useState(false);
  const [caps, setCaps] = useState(false);
  const auto = useId();
  const fid = id ?? auto;
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => setCaps(e.getModifierState?.("CapsLock") ?? false);
  return (
    <div>
      <label htmlFor={fid} className="text-sm font-semibold text-forest-950">{label}</label>
      <div className="relative mt-1.5">
        <input
          id={fid}
          {...rest}
          type={show ? "text" : "password"}
          onKeyDown={onKey}
          onKeyUp={onKey}
          aria-invalid={!!error}
          aria-describedby={error || hint ? `${fid}-msg` : undefined}
          className={`${inputBase} pl-10 pr-12 ${error ? inputBad : inputOk}`}
        />
        <Lock size={17} className={iconCls} />
        <button
          type="button"
          onClick={() => setShow((s) => !s)}
          className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-lg p-2 text-sage-600 transition hover:bg-sage-100 hover:text-forest-800"
          aria-label={show ? "Hide password" : "Show password"}
          aria-pressed={show}
        >
          {show ? <EyeOff size={17} /> : <Eye size={17} />}
        </button>
      </div>
      {caps && <p className="mt-1.5 animate-slide-down text-xs text-amber-700">Caps Lock is on.</p>}
      {error ? (
        <p id={`${fid}-msg`} className="mt-1.5 flex animate-slide-down items-center gap-1 text-xs text-red-700">
          <AlertTriangle size={12} className="shrink-0" /> {error}
        </p>
      ) : (
        hint && (
          <p id={`${fid}-msg`} className={`mt-1.5 flex animate-slide-down items-center gap-1 text-xs ${hintOk ? "text-leaf-700" : "text-amber-700"}`}>
            {hintOk ? <CheckCircle2 size={12} className="shrink-0" /> : <AlertTriangle size={12} className="shrink-0" />} {hint}
          </p>
        )
      )}
    </div>
  );
}

/** Weak / medium / strong: strong requires every rule and at least 12 characters. */
function strengthOf(password: string) {
  const met = PASSWORD_RULES.filter((r) => r.test(password)).length;
  if (!password) return null;
  if (met === PASSWORD_RULES.length && password.length >= 12) return { level: 3, label: "Strong", bar: "bg-leaf-600", text: "text-leaf-700" };
  if (met >= PASSWORD_RULES.length - 1) return { level: 2, label: "Medium", bar: "bg-amber-500", text: "text-amber-700" };
  return { level: 1, label: "Weak", bar: "bg-red-500", text: "text-red-700" };
}

export function PasswordChecklist({ password }: { password: string }) {
  const s = strengthOf(password);
  return (
    <div className="mt-2.5 rounded-xl bg-cream-100/70 p-3 short:mt-2 short:p-2.5">
      <div className="flex items-center gap-3">
        <div className="flex flex-1 gap-1.5" aria-hidden="true">
          {[1, 2, 3].map((i) => (
            <span key={i} className={`h-1.5 flex-1 rounded-full transition-colors duration-300 ${s && i <= s.level ? s.bar : "bg-sage-200"}`} />
          ))}
        </div>
        <span className={`w-16 text-right text-xs font-semibold ${s ? s.text : "text-slate-400"}`} aria-live="polite">
          {s ? s.label : "Strength"}
        </span>
      </div>
      <ul className="mt-2.5 grid grid-cols-2 gap-x-3 gap-y-1 text-xs short:mt-2 short:empty:hidden" aria-label="Password requirements">
        {PASSWORD_RULES.map((r) => {
          const ok = r.test(password);
          return (
            <li key={r.label} className={`flex items-center gap-1.5 transition-colors duration-200 ${ok ? "text-leaf-700 short:hidden" : "text-slate-500"}`}>
              <CheckCircle2 size={13} className={`shrink-0 transition-opacity duration-200 ${ok ? "" : "opacity-35"}`} /> {r.label}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function Alert({ kind = "error", children }: { kind?: "error" | "success" | "info"; children: ReactNode }) {
  const cls = {
    error: "border-red-200 bg-red-50 text-red-800 animate-shake",
    success: "border-leaf-200 bg-leaf-50 text-leaf-700 animate-slide-down",
    info: "border-sage-200 bg-cream-50 text-slate-700 animate-slide-down",
  }[kind];
  return (
    <div role={kind === "error" ? "alert" : "status"} className={`mb-5 flex gap-2.5 rounded-xl border p-3 text-sm ${cls}`}>
      {kind === "error" ? <AlertTriangle size={17} className="mt-0.5 shrink-0" /> : kind === "info" ? <Info size={17} className="mt-0.5 shrink-0 text-sage-600" /> : <CheckCircle2 size={17} className="mt-0.5 shrink-0" />}
      <div className="min-w-0">{children}</div>
    </div>
  );
}

/** One real input (paste, autofill of one-time codes, screen readers) shown as six boxes. */
export function CodeField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const id = useId();
  const [focused, setFocused] = useState(false);
  const active = Math.min(value.length, 5);
  return (
    <div>
      <label htmlFor={id} className="text-sm font-semibold text-forest-950">6-digit code</label>
      <div className="relative mt-1.5">
        <div className="grid grid-cols-6 gap-2" aria-hidden="true">
          {Array.from({ length: 6 }, (_, i) => (
            <div
              key={i}
              className={`grid h-14 short:h-12 place-items-center rounded-xl border-2 font-mono text-2xl font-semibold transition duration-200 ease-smooth ${
                focused && i === active
                  ? "border-leaf-500 bg-white ring-4 ring-lime-300/40"
                  : value[i]
                    ? "border-leaf-200 bg-leaf-50 text-forest-900"
                    : "border-sage-200 bg-cream-50"
              }`}
            >
              {value[i] ?? (focused && i === active ? <span className="h-6 w-0.5 animate-pulse rounded bg-leaf-600" /> : "")}
            </div>
          ))}
        </div>
        <input
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 6))}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          className="absolute inset-0 h-full w-full cursor-text rounded-xl bg-transparent text-transparent caret-transparent opacity-0 focus:outline-none"
        />
      </div>
    </div>
  );
}
