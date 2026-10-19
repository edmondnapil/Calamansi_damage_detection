import { Activity as ActivityIcon, ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { btn, Card, CardHeader, EmptyState, ErrorBox, Spinner } from "../../components/ui";
import { api } from "../../lib/api";
import { dateTime } from "../../lib/format";
import type { ActivityEvent } from "../../lib/types";
import { useAsync } from "../../lib/useAsync";

const LABELS: Record<string, string> = {
  register: "Registration",
  signup_code_sent: "Verification code sent",
  signup_verify: "Email verification",
  login: "Sign-in",
  logout: "Sign-out",
  recovery_code_sent: "Password reset code sent",
  recovery_verify: "Password reset code check",
  password_reset: "Password reset",
  password_change: "Password change",
  admin_user_update: "Admin: account updated",
  admin_user_delete: "Admin: account deleted",
  admin_provisioned: "Administrator provisioned",
  account_status_change: "Admin: status changed",
};

export const eventLabel = (t: string) => LABELS[t] ?? t.replace(/_/g, " ");

export function StatusPill({ status }: { status: ActivityEvent["event_status"] }) {
  const cls = { success: "bg-leaf-100 text-leaf-700", failure: "bg-amber-100 text-amber-700", blocked: "bg-red-50 text-red-700" }[status];
  return <span className={`inline-flex w-[68px] shrink-0 justify-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{status}</span>;
}

/** Security events recorded by the server. E-mails and IPs are stored only as keyed hashes and are never shown. */
export default function AdminActivity() {
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const log = useAsync(() => api.adminActivity({ event_type: type || undefined, status: status || undefined, page, page_size: 25 }), [type, status, page]);
  const d = log.data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Security activity</h1>
        <p className="mt-1 text-sm text-slate-600">Sign-ins, registrations, verification, password and administrator actions, newest first.</p>
      </div>
      <Card>
        <CardHeader icon={<ActivityIcon size={19} />} title="Activity log" action={d && <span className="text-sm text-slate-500">{d.total} events</span>} />
        <div className="flex flex-wrap gap-3 p-5">
          <select value={type} onChange={(e) => { setType(e.target.value); setPage(1); }} className={`${btn.input} w-auto`} aria-label="Event type">
            <option value="">All events</option>
            {Object.entries(LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className={`${btn.input} w-auto`} aria-label="Result">
            <option value="">All results</option>
            <option value="success">Success</option>
            <option value="failure">Failure</option>
            <option value="blocked">Blocked</option>
          </select>
        </div>
        {log.loading && !d ? (
          <Spinner />
        ) : log.error ? (
          <ErrorBox message={log.error} onRetry={log.reload} />
        ) : !d?.items.length ? (
          <EmptyState title="No matching events" />
        ) : (
          <>
            <div className={`relative overflow-x-auto transition-opacity duration-200 ${log.loading ? "opacity-60" : ""}`}>
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead>
                  <tr className="bg-mint-50 text-xs font-semibold text-slate-600">
                    <th className="px-4 py-2.5">Time</th>
                    <th className="px-4 py-2.5">Event</th>
                    <th className="px-4 py-2.5">Result</th>
                    <th className="px-4 py-2.5">Account</th>
                    <th className="px-4 py-2.5">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-leaf-100">
                  {d.items.map((e) => (
                    <tr key={e.id} className="transition-colors hover:bg-mint-50/60">
                      <td className="whitespace-nowrap px-4 py-2.5 text-slate-600">{dateTime(e.created_at)}</td>
                      <td className="px-4 py-2.5 font-medium">{eventLabel(e.event_type)}</td>
                      <td className="px-4 py-2.5"><StatusPill status={e.event_status} /></td>
                      <td className="px-4 py-2.5 text-slate-600">{e.user_name ?? <span className="text-slate-400">—</span>}</td>
                      <td className="px-4 py-2.5 text-xs text-slate-500">
                        {Object.entries(e.details ?? {}).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`).join(" · ") || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-leaf-100 px-5 py-3 text-sm">
              <span className="text-slate-500">Page {d.page} of {d.pages}</span>
              <div className="flex gap-2">
                <button className={btn.secondary} disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft size={16} /> Previous</button>
                <button className={btn.secondary} disabled={page >= d.pages} onClick={() => setPage(page + 1)}>Next <ChevronRight size={16} /></button>
              </div>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
