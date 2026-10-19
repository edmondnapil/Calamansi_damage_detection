import { CheckCircle2, ChevronDown, KeyRound, LogOut, RefreshCw, ShieldCheck, XCircle, type LucideIcon } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dateTime, loadPrefs, pct, savePrefs } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import ChangePasswordForm from "./ChangePasswordForm";
import { useToast } from "./Feedback";
import ModelMetrics, { LeafCheckMetrics } from "./ModelMetrics";
import { btn, Card, ErrorBox, Spinner } from "./ui";

export interface SettingsTab {
  id: string;
  label: string;
  icon: LucideIcon;
  /** Old links (e.g. #about) that should open this tab. */
  aliases?: string[];
  render: () => ReactNode;
}

/** Page header + tab bar; the open tab is kept in the URL hash so links and Back work. */
export function SettingsPage({ title, subtitle, tabs }: { title: string; subtitle: string; tabs: SettingsTab[] }) {
  const { hash, pathname } = useLocation();
  const navigate = useNavigate();
  const key = hash.replace("#", "");
  const active = tabs.find((t) => t.id === key || t.aliases?.includes(key)) ?? tabs[0];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{title}</h1>
        <p className="mt-1 text-sm text-slate-600">{subtitle}</p>
      </div>
      <div role="tablist" aria-label={title} className="-mx-1 flex gap-1 overflow-x-auto border-b border-leaf-100 px-1">
        {tabs.map((t) => {
          const on = t.id === active.id;
          return (
            <button
              key={t.id}
              role="tab"
              aria-selected={on}
              onClick={() => navigate(`${pathname}#${t.id}`, { replace: true })}
              className={`-mb-px inline-flex shrink-0 items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors duration-200 ease-smooth ${
                on ? "border-leaf-600 text-forest-950" : "border-transparent text-slate-500 hover:text-forest-800"
              }`}
            >
              <t.icon size={16} className={on ? "text-leaf-600" : ""} />
              {t.label}
            </button>
          );
        })}
      </div>
      <div key={active.id} role="tabpanel" className="animate-fade-in">
        {active.render()}
      </div>
    </div>
  );
}

/** One setting: label and short explanation on the left, the value or control on the right. */
function Row({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-leaf-100 px-5 py-4 last:border-0">
      <div className="min-w-0">
        <p className="text-sm font-medium text-forest-950">{label}</p>
        {hint && <p className="mt-0.5 text-xs text-slate-500">{hint}</p>}
      </div>
      <div className="min-w-0 break-words text-right text-sm">{children}</div>
    </div>
  );
}

function Section({ title, action, children, className = "" }: { title: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <Card className={className}>
      <div className="flex items-center justify-between gap-3 border-b border-leaf-100 px-5 py-3.5">
        <h2 className="text-[15px] font-semibold text-forest-950">{title}</h2>
        {action}
      </div>
      {children}
    </Card>
  );
}

function Status({ ok, children }: { ok: boolean; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1.5 font-medium ${ok ? "text-leaf-700" : "text-red-700"}`}>
      {ok ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
      {children}
    </span>
  );
}

export function AccountPanel() {
  const { user, signOut } = useAuth();
  const toast = useToast();
  if (!user) return null;
  const isAdmin = user.role === "admin";
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_1.15fr] [&>*]:min-w-0">
      <Section title="Profile">
        <div className="flex items-center gap-4 border-b border-leaf-100 px-5 py-5">
          <span className="grid h-14 w-14 shrink-0 place-items-center rounded-full bg-forest-800 text-xl font-bold text-white">
            {(user.full_name || user.username).charAt(0).toUpperCase()}
          </span>
          <div className="min-w-0">
            <p className="truncate font-semibold text-forest-950">{user.full_name}</p>
            <p className="truncate text-sm text-slate-500">@{user.username}</p>
            {isAdmin && (
              <span className="mt-1 inline-flex items-center gap-1 rounded-full bg-forest-800 px-2 py-0.5 text-[11px] font-medium text-white">
                <ShieldCheck size={11} /> Administrator
              </span>
            )}
          </div>
        </div>
        <Row label="Email">{user.email}</Row>
        <Row label="Email verified">
          <Status ok={user.email_verified}>{user.email_verified ? "Verified" : "Not verified"}</Status>
        </Row>
        <Row label="Account status">
          <Status ok={user.account_status === "active"}>{user.account_status === "active" ? "Active" : "Suspended"}</Status>
        </Row>
        {isAdmin && (
          <p className="mx-5 mt-4 flex gap-2 rounded-xl bg-leaf-50 p-3 text-xs text-forest-900">
            <ShieldCheck size={15} className="mt-0.5 shrink-0 text-leaf-700" />
            Administrator rights can only be granted on the server (create_admin.py or SQL), never from the website.
          </p>
        )}
        <div className="p-5">
          <button
            onClick={() => void signOut()}
            className="inline-flex items-center gap-2 rounded-xl border border-red-200 px-4 py-2.5 text-sm font-semibold text-red-700 transition hover:bg-red-50"
          >
            <LogOut size={16} /> Sign out
          </button>
        </div>
      </Section>
      <Section title="Change password" action={<KeyRound size={17} className="text-leaf-600" />}>
        <div className="p-5">
          <ChangePasswordForm onDone={(m) => toast("success", m)} />
        </div>
      </Section>
    </div>
  );
}

export function PreferencesPanel() {
  const [prefs, setPrefs] = useState(loadPrefs());
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (!saved) return;
    const t = setTimeout(() => setSaved(false), 1500);
    return () => clearTimeout(t);
  }, [saved]);
  const update = (patch: Partial<typeof prefs>) => {
    const next = { ...prefs, ...patch };
    setPrefs(next);
    savePrefs(next);
    setSaved(true);
  };
  const select = `${btn.input} w-40`;
  return (
    <Section
      className="max-w-3xl"
      title="Interface preferences"
      action={<span className={`text-xs text-leaf-700 transition-opacity ${saved ? "opacity-100" : "opacity-0"}`}>Saved</span>}
    >
      <Row label="Dashboard chart range" hint="Period shown when the dashboard opens.">
        <select value={prefs.chartDays} onChange={(e) => update({ chartDays: Number(e.target.value) })} className={select} aria-label="Dashboard chart range">
          {[7, 14, 30].map((d) => (
            <option key={d} value={d}>
              Last {d} days
            </option>
          ))}
        </select>
      </Row>
      <Row label="Rows per page in Logs" hint="Number of detections listed per page.">
        <select value={prefs.pageSize} onChange={(e) => update({ pageSize: Number(e.target.value) })} className={select} aria-label="Rows per page in Logs">
          {[10, 20, 50].map((n) => (
            <option key={n} value={n}>
              {n} rows
            </option>
          ))}
        </select>
      </Row>
      <p className="px-5 py-3 text-xs text-slate-500">Saved automatically, in this browser only.</p>
    </Section>
  );
}

export function SystemPanel() {
  const health = useAsync(() => api.health(), []);
  const h = health.data;
  return (
    <Section
      className="max-w-3xl"
      title="System status"
      action={
        <button onClick={health.reload} className="rounded-lg p-1.5 text-slate-500 transition hover:bg-mint-100" aria-label="Refresh status">
          <RefreshCw size={15} />
        </button>
      }
    >
      {health.loading ? (
        <div className="p-5">
          <Spinner />
        </div>
      ) : health.error ? (
        <div className="p-5">
          <ErrorBox message={health.error} onRetry={health.reload} />
        </div>
      ) : (
        h && (
          <>
            <Row label="Backend API">
              <Status ok>Online</Status>
            </Row>
            <Row label="Classification model">
              <Status ok={h.model.loaded}>{h.model.loaded ? "Loaded" : "Not loaded"}</Status>
            </Row>
            <Row label="Calamansi-leaf check" hint="Rejects photos that are not calamansi leaves.">
              <Status ok={h.leaf_check.loaded}>{h.leaf_check.loaded ? "Active" : "Not loaded"}</Status>
            </Row>
            <Row label="Database">
              <Status ok={h.database.connected}>
                {h.database.backend === "supabase" ? "Supabase" : h.database.backend === "local" ? "Local SQLite (fallback)" : "None"}{" "}
                {h.database.connected ? "connected" : "unavailable"}
              </Status>
            </Row>
            {h.database.backend === "supabase" && <Row label="Storage bucket">{h.database.bucket}</Row>}
            <Row label="Image retention">{h.image_retention ? "On (images kept for history)" : "Off (results only)"}</Row>
            <Row label="Upload limit">{h.max_upload_mb} MB</Row>
            <Row label="Timezone">{h.timezone}</Row>
            {(h.database.error || h.database.note || h.model.error) && (
              <p className="mx-5 mb-4 rounded-xl bg-amber-50 p-3 text-xs text-amber-700">{h.database.error || h.model.error || h.database.note}</p>
            )}
            <p className="px-5 py-3 text-xs text-slate-500">Credentials are kept on the server and are never shown here.</p>
          </>
        )
      )}
    </Section>
  );
}

function Details({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="group rounded-2xl border border-leaf-100 bg-white shadow-card">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4 text-[15px] font-semibold text-forest-950 [&::-webkit-details-marker]:hidden">
        {title}
        <ChevronDown size={18} className="text-slate-400 transition-transform duration-200 group-open:rotate-180" />
      </summary>
      <div className="border-t border-leaf-100 [&>section]:rounded-none [&>section]:border-0 [&>section]:shadow-none [&>section>div:first-child]:hidden">{children}</div>
    </details>
  );
}

export function ModelPanel() {
  const model = useAsync(() => api.model(), []);
  if (model.loading) return <Spinner />;
  if (model.error) return <ErrorBox message={model.error} onRetry={model.reload} />;
  const info = model.data;
  const meta = info?.metadata;
  if (!info || !meta) return <p className="text-sm text-slate-500">No trained model found. Run train_model.py.</p>;
  const ev = info.evaluation;
  const lc = info.leaf_check?.calamansi_test_acceptance;
  const tiles: [string, string, string][] = [
    ["Test accuracy", pct(ev?.test.accuracy), ev ? `${ev.test.n} independent test photos` : "Not evaluated yet"],
    ["Validation accuracy", pct(meta.validation.accuracy), "Used to choose the model"],
    ["Calamansi photos accepted", pct(lc?.all_photos), lc ? "By the calamansi-leaf check" : "Leaf check not evaluated"],
    ["Training photos", String(meta.train_counts.Healthy + meta.train_counts.Damaged), `${meta.train_counts.Healthy} Healthy · ${meta.train_counts.Damaged} Damaged`],
  ];
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {tiles.map(([k, v, s]) => (
          <Card key={k} className="p-5">
            <p className="text-xs text-slate-500">{k}</p>
            <p className="mt-1 text-2xl font-bold text-forest-950">{v}</p>
            <p className="mt-1 text-xs text-slate-500">{s}</p>
          </Card>
        ))}
      </div>
      <Section title="Model details">
        <Row label="Architecture">{meta.architecture === "mobilenetv2" ? "MobileNetV2 (transfer learning)" : "EfficientNetB0 (transfer learning)"}</Row>
        <Row label="Version">
          <span className="font-mono text-xs">{meta.model_version}</span>
        </Row>
        <Row label="Trained">{dateTime(meta.trained_at)}</Row>
        <Row label="Input size">
          {meta.img_size} × {meta.img_size} px
        </Row>
        <Row label="Classes">Healthy, Damaged</Row>
        {meta.candidates.length > 1 && <Row label="Candidates compared">{meta.candidates.map((c) => `${c.arch} ${pct(c.val_accuracy)}`).join(" · ")}</Row>}
      </Section>
      <div className="space-y-3">
        <Details title="Classifier results on the independent test set">
          <ModelMetrics info={info} />
        </Details>
        {info.leaf_check && (
          <Details title="Calamansi-leaf check results on held-out test images">
            <LeafCheckMetrics info={info} />
          </Details>
        )}
      </div>
    </div>
  );
}
