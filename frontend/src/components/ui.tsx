import { AlertTriangle, ArrowDownRight, ArrowUpRight, CheckCircle2, Inbox, Leaf, Loader2, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import type { LeafClass } from "../lib/types";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-2xl border border-leaf-100 bg-white shadow-card transition-shadow duration-250 ease-smooth ${className}`}>{children}</section>;
}

export function CardHeader({ icon, title, action }: { icon?: ReactNode; title: string; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 px-5 pt-5">
      <h2 className="flex items-center gap-2.5 text-[15px] font-semibold text-forest-950">
        {icon && <span className="text-leaf-600">{icon}</span>}
        {title}
      </h2>
      {action}
    </div>
  );
}

export function LeafLogo({ size = 40 }: { size?: number }) {
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-full bg-leaf-600 text-white ring-4 ring-white/10"
      style={{ width: size, height: size }}
    >
      <Leaf size={size * 0.5} strokeWidth={2.2} />
    </span>
  );
}

/** Green for Healthy, amber for Damaged - always paired with an icon and text. */
export function ResultBadge({ value, size = "sm" }: { value: LeafClass; size?: "sm" | "md" }) {
  const healthy = value === "Healthy";
  const Icon = healthy ? CheckCircle2 : AlertTriangle;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium ${
        size === "md" ? "px-3 py-1 text-sm" : "px-2.5 py-0.5 text-xs"
      } ${healthy ? "bg-leaf-100 text-leaf-700" : "bg-amber-100 text-amber-700"}`}
    >
      <Icon size={size === "md" ? 15 : 13} />
      {value}
    </span>
  );
}

export function StatusIcon({ value, size = 44 }: { value: LeafClass; size?: number }) {
  const healthy = value === "Healthy";
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-full text-white ${healthy ? "bg-leaf-600" : "bg-amber-500"}`}
      style={{ width: size, height: size }}
    >
      {healthy ? <Leaf size={size * 0.48} /> : <AlertTriangle size={size * 0.48} />}
    </span>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500">
      <Loader2 className="animate-spin text-leaf-600" size={18} /> {label}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="m-5 flex flex-wrap items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      <AlertTriangle size={18} className="mt-0.5 shrink-0" />
      <p className="min-w-0 flex-1">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="inline-flex items-center gap-1 font-medium text-red-700 hover:underline">
          <RefreshCw size={14} /> Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-10 text-center">
      <span className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full bg-mint-100 text-leaf-600">
        <Inbox size={22} />
      </span>
      <p className="font-medium text-forest-950">{title}</p>
      {children && <div className="mt-1 max-w-sm text-sm text-slate-500">{children}</div>}
    </div>
  );
}

const STAT_TONES = {
  green: "bg-leaf-50 text-leaf-700 ring-leaf-100",
  amber: "bg-amber-50 text-amber-700 ring-amber-100",
  forest: "bg-mint-100 text-forest-800 ring-leaf-100",
  red: "bg-red-50 text-red-700 ring-red-100",
  slate: "bg-slate-100 text-slate-700 ring-slate-200",
};

/** Compact figure tile: label + icon, the number, then an optional change badge and/or a note. */
export function StatCard({
  icon,
  tone,
  label,
  value,
  change,
  caption,
  sub,
}: {
  icon: ReactNode;
  tone: keyof typeof STAT_TONES;
  label: string;
  value: number | string;
  /** Percentage change against the previous period; null = no earlier data; omit to hide. */
  change?: number | null;
  caption?: string;
  sub?: ReactNode;
}) {
  const up = (change ?? 0) >= 0;
  return (
    <Card className="flex h-full flex-col p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-slate-500">{label}</p>
        <span className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ring-1 ${STAT_TONES[tone]}`}>{icon}</span>
      </div>
      <p className="mt-1 text-[28px] font-bold leading-none tracking-tight tabular-nums text-forest-950">{value}</p>
      <div className="mt-auto pt-3 text-xs text-slate-500">
        {change !== undefined && (
          <p className="flex flex-wrap items-center gap-1.5">
            {change === null ? (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-500">No earlier data</span>
            ) : (
              <span className={`inline-flex items-center rounded-full px-2 py-0.5 font-semibold ${up ? "bg-leaf-50 text-leaf-700" : "bg-amber-50 text-amber-700"}`}>
                {up ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
                {Math.abs(change)}%
              </span>
            )}
            {caption && <span>{caption}</span>}
          </p>
        )}
        {sub && <p className={change !== undefined ? "mt-1" : ""}>{sub}</p>}
      </div>
    </Card>
  );
}

/** Small uppercase heading that groups the cards below it. */
export function SectionLabel({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">{children}</h2>
      {action}
    </div>
  );
}

export function Thumb({ src, alt, size = 36 }: { src?: string; alt: string; size?: number }) {
  return src ? (
    <img src={src} alt={alt} loading="lazy" className="rounded-md object-cover ring-1 ring-leaf-100" style={{ width: size, height: size }} />
  ) : (
    <span
      className="inline-flex items-center justify-center rounded-md bg-mint-100 text-leaf-500"
      style={{ width: size, height: size }}
      title="Image not retained"
    >
      <Leaf size={size * 0.45} />
    </span>
  );
}

export const btn = {
  primary:
    "inline-flex items-center justify-center gap-2 rounded-xl bg-forest-800 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition duration-200 ease-smooth hover:bg-forest-700 hover:shadow-md active:scale-[0.98] focus:outline-none focus-visible:ring-2 focus-visible:ring-leaf-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 disabled:active:scale-100",
  secondary:
    "inline-flex items-center justify-center gap-2 rounded-xl border border-leaf-200 bg-white px-4 py-2.5 text-sm font-semibold text-forest-800 transition duration-200 ease-smooth hover:border-leaf-500/40 hover:bg-mint-50 active:scale-[0.98] focus:outline-none focus-visible:ring-2 focus-visible:ring-leaf-500 disabled:opacity-60 disabled:active:scale-100",
  input:
    "w-full rounded-xl border border-leaf-100 bg-mint-50 px-3 py-2 text-sm text-forest-950 placeholder:text-slate-400 transition duration-200 ease-smooth hover:border-leaf-200 focus:border-leaf-500 focus:bg-white focus:outline-none focus:ring-4 focus:ring-leaf-100",
};
