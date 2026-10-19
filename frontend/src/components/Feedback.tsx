import { AlertTriangle, CheckCircle2, Loader2, X } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

// --------------------------------------------------------------------------- toasts
type Toast = { id: number; kind: "success" | "error"; text: string };
const ToastContext = createContext<(kind: Toast["kind"], text: string) => void>(() => {});

/** Short success/error messages after an action; dismissed automatically after 4 s. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((kind: Toast["kind"], text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-2), { id, kind, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.kind === "error" ? "alert" : "status"}
            className={`pointer-events-auto flex animate-slide-in-right items-start gap-2.5 rounded-xl border bg-white p-3.5 text-sm shadow-lift ${
              t.kind === "error" ? "border-red-200 text-red-800" : "border-leaf-200 text-forest-950"
            }`}
          >
            {t.kind === "error" ? <AlertTriangle size={18} className="mt-0.5 shrink-0 text-red-600" /> : <CheckCircle2 size={18} className="mt-0.5 shrink-0 text-leaf-600" />}
            <p className="min-w-0 flex-1">{t.text}</p>
            <button onClick={() => setToasts((all) => all.filter((x) => x.id !== t.id))} className="rounded p-0.5 text-slate-400 hover:text-slate-600" aria-label="Dismiss">
              <X size={15} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

// --------------------------------------------------------------------------- modal
export function Modal({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLElement>("input, select, textarea, button")?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      prev?.focus();
    };
  }, [onClose]);
  // Rendered at <body> level: an animated (transformed) ancestor would otherwise trap position: fixed.
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-forest-950/45 p-0 animate-fade-in sm:items-center sm:p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`max-h-[92vh] w-full overflow-y-auto rounded-t-2xl bg-white p-5 shadow-lift animate-scale-in sm:rounded-2xl ${wide ? "sm:max-w-2xl" : "sm:max-w-md"}`}
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-forest-950">{title}</h2>
          <button onClick={onClose} className="rounded-lg p-1.5 text-slate-500 transition hover:bg-mint-100" aria-label="Close">
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}

/** Destructive confirmation: the user must type `confirmWord` to enable the button. */
export function ConfirmDialog({
  title,
  message,
  confirmLabel,
  confirmWord,
  busy,
  onConfirm,
  onClose,
}: {
  title: string;
  message: ReactNode;
  confirmLabel: string;
  confirmWord?: string;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const [typed, setTyped] = useState("");
  const ok = !confirmWord || typed.trim() === confirmWord;
  return (
    <Modal title={title} onClose={onClose}>
      <div className="flex gap-3 rounded-xl bg-red-50 p-3 text-sm text-red-800">
        <AlertTriangle size={18} className="mt-0.5 shrink-0" />
        <div>{message}</div>
      </div>
      {confirmWord && (
        <label className="mt-4 block text-sm">
          <span className="text-slate-600">
            Type <strong className="font-mono text-forest-950">{confirmWord}</strong> to confirm
          </span>
          <input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            className="mt-1 w-full rounded-xl border border-leaf-100 px-3 py-2 text-sm transition focus:border-red-300 focus:outline-none focus:ring-2 focus:ring-red-100"
          />
        </label>
      )}
      <div className="mt-5 flex justify-end gap-2">
        <button onClick={onClose} className="rounded-xl border border-leaf-200 px-4 py-2.5 text-sm font-semibold text-forest-800 transition hover:bg-mint-50">
          Cancel
        </button>
        <button
          onClick={onConfirm}
          disabled={!ok || busy}
          className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-red-700 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy && <Loader2 size={15} className="animate-spin" />} {confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
