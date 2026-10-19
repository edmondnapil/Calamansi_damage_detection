import { ChevronLeft, ChevronRight, Eye, Loader2, RotateCcw, Save, Search, ShieldCheck, Trash2, Users as UsersIcon } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { Field } from "../../components/AuthShell";
import { ConfirmDialog, Modal, useToast } from "../../components/Feedback";
import { btn, Card, CardHeader, EmptyState, ErrorBox, ResultBadge, Spinner } from "../../components/ui";
import { api, ApiError } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { dateTime, pct } from "../../lib/format";
import type { AdminUser } from "../../lib/types";
import { useAsync } from "../../lib/useAsync";

function StatusBadge({ u }: { u: AdminUser }) {
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${u.account_status === "active" ? "bg-leaf-100 text-leaf-700" : "bg-red-50 text-red-700"}`}>
      {u.account_status === "active" ? "Active" : "Suspended"}
    </span>
  );
}

function RoleBadge({ role }: { role: AdminUser["role"] }) {
  return role === "admin" ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-forest-800 px-2.5 py-0.5 text-xs font-medium text-white"><ShieldCheck size={12} /> Admin</span>
  ) : (
    <span className="text-sm text-slate-600">User</span>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3 border-b border-leaf-100 py-2 text-sm last:border-0">
      <span className="text-slate-500">{label}</span>
      <span className="min-w-0 break-words text-right font-medium">{children}</span>
    </div>
  );
}

function UserDetail({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const { user: me } = useAuth();
  const toast = useToast();
  const detail = useAsync(() => api.adminUser(id), [id]);
  const [form, setForm] = useState({ full_name: "", username: "", account_status: "active" as "active" | "suspended" });
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [confirmDelete, setConfirmDelete] = useState(false);
  const d = detail.data;
  const self = d?.id === me?.id;
  const protectedAccount = self || d?.role === "admin";

  useEffect(() => {
    if (d) setForm({ full_name: d.full_name, username: d.username, account_status: d.account_status });
  }, [d]);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!d || busy) return;
    const v: Record<string, string> = {};
    if (!form.full_name.trim()) v.full_name = "Enter a name.";
    if (!/^[a-z0-9_]{3,30}$/.test(form.username.trim().toLowerCase())) v.username = "3–30 characters: letters, numbers or _.";
    setErrors(v);
    if (Object.keys(v).length) return;
    setBusy(true);
    try {
      const res = await api.updateUser(d.id, {
        full_name: form.full_name.trim(),
        username: form.username.trim().toLowerCase(),
        ...(self ? {} : { account_status: form.account_status }),
      });
      toast("success", res.message);
      detail.reload();
      onChanged();
    } catch (err) {
      const e2 = err as ApiError;
      if (e2.code === "username_taken" || e2.code === "invalid_username") setErrors({ username: e2.message });
      else toast("error", e2.message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!d) return;
    setBusy(true);
    try {
      const res = await api.deleteUser(d.id);
      toast("success", res.message);
      onChanged();
      onClose();
    } catch (err) {
      toast("error", (err as ApiError).message);
    } finally {
      setBusy(false);
      setConfirmDelete(false);
    }
  };

  return (
    <Modal title="Account details" onClose={onClose} wide>
      {detail.loading && !d ? (
        <Spinner />
      ) : detail.error ? (
        <ErrorBox message={detail.error} onRetry={detail.reload} />
      ) : (
        d && (
          <div className="grid gap-6 md:grid-cols-2">
            <div>
              <div className="mb-3 flex items-center gap-3">
                <span className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-forest-800 text-lg font-semibold text-white">{d.full_name.charAt(0).toUpperCase()}</span>
                <div className="min-w-0">
                  <p className="truncate font-semibold">{d.full_name}</p>
                  <p className="truncate text-sm text-slate-500">@{d.username}</p>
                </div>
              </div>
              <Row label="Email">{d.email ?? "—"}</Row>
              <Row label="Role"><RoleBadge role={d.role} /></Row>
              <Row label="Status"><StatusBadge u={d} /></Row>
              <Row label="Email verified">{d.email_verified_at ? dateTime(d.email_verified_at) : <span className="text-amber-700">Not verified</span>}</Row>
              <Row label="Registered">{dateTime(d.created_at)}</Row>
              <Row label="Last sign-in">{d.last_sign_in_at ? dateTime(d.last_sign_in_at) : "Never"}</Row>
              {d.must_change_password && <Row label="Password">Temporary (must be changed)</Row>}
              <p className="mb-2 mt-5 text-sm font-semibold">Detections</p>
              <div className="grid grid-cols-3 gap-2 text-center">
                {[["Total", d.detections.total], ["Healthy", d.detections.healthy], ["Damaged", d.detections.damaged]].map(([k, v]) => (
                  <div key={k} className="rounded-xl bg-mint-50 p-2.5">
                    <p className="text-lg font-bold">{v}</p>
                    <p className="text-xs text-slate-500">{k}</p>
                  </div>
                ))}
              </div>
              {d.detections.recent.length > 0 && (
                <ul className="mt-3 space-y-1.5 text-sm">
                  {d.detections.recent.map((r) => (
                    <li key={r.id} className="flex items-center gap-2">
                      <ResultBadge value={r.predicted_class} />
                      <span className="tabular-nums text-slate-600">{pct(r.confidence)}</span>
                      <span className="ml-auto text-xs text-slate-500">{dateTime(r.created_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <form onSubmit={save} className="space-y-4" noValidate>
                <p className="text-sm font-semibold">Edit account</p>
                <Field label="Full name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} error={errors.full_name} maxLength={100} />
                <Field label="Username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} error={errors.username} maxLength={30} />
                <label className="block">
                  <span className="text-sm font-medium text-forest-950">Account status</span>
                  <select
                    value={form.account_status}
                    disabled={self}
                    onChange={(e) => setForm({ ...form, account_status: e.target.value as "active" | "suspended" })}
                    className={`${btn.input} mt-1.5`}
                  >
                    <option value="active">Active: can sign in</option>
                    <option value="suspended">Suspended: cannot sign in</option>
                  </select>
                  {self && <span className="mt-1 block text-xs text-slate-500">You cannot suspend your own account.</span>}
                </label>
                <button type="submit" disabled={busy} className={`${btn.primary} w-full`}>
                  {busy ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />} Save changes
                </button>
              </form>
              <div className="mt-6 rounded-xl border border-red-200 p-4">
                <p className="text-sm font-semibold text-red-700">Delete account</p>
                <p className="mt-1 text-xs text-slate-600">
                  {protectedAccount
                    ? "Your own account and administrator accounts cannot be deleted here."
                    : "Permanently deletes the account, its detections and their images. This cannot be undone."}
                </p>
                <button
                  onClick={() => setConfirmDelete(true)}
                  disabled={protectedAccount || busy}
                  className="mt-3 inline-flex items-center gap-2 rounded-xl border border-red-300 px-3 py-2 text-sm font-semibold text-red-700 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Trash2 size={15} /> Delete account
                </button>
              </div>
            </div>
          </div>
        )
      )}
      {confirmDelete && d && (
        <ConfirmDialog
          title="Delete this account?"
          message={<>This permanently deletes <strong>{d.full_name}</strong> ({d.email}), {d.detections.total} detection(s) and their images.</>}
          confirmLabel="Delete permanently"
          confirmWord={d.username}
          busy={busy}
          onConfirm={remove}
          onClose={() => setConfirmDelete(false)}
        />
      )}
    </Modal>
  );
}

export default function AdminUsers() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const status = params.get("status") ?? "";
  const role = params.get("role") ?? "";
  const verified = params.get("verified") ?? "";
  const page = Number(params.get("page") ?? "1") || 1;
  const [draft, setDraft] = useState(q);
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    setDraft(q);
  }, [q]);
  const users = useAsync(() => api.adminUsers({ q, status, role, verified, page, page_size: 15 }), [q, status, role, verified, page]);
  const d = users.data;

  const update = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    if (!("page" in patch)) next.delete("page");
    setParams(next);
  };
  const filtered = !!(q || status || role || verified);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">User management</h1>
        <p className="mt-1 text-sm text-slate-600">Search, review, edit, suspend or delete accounts. New accounts always start as ordinary users.</p>
      </div>
      <Card>
        <CardHeader icon={<UsersIcon size={19} />} title="Accounts" action={d && <span className="text-sm text-slate-500">{d.total} found</span>} />
        <div className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr_auto]">
          <form onSubmit={(e) => { e.preventDefault(); update({ q: draft.trim() }); }} className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input value={draft} onChange={(e) => setDraft(e.target.value)} onBlur={() => draft.trim() !== q && update({ q: draft.trim() })} placeholder="Name, username or email" className={`${btn.input} pl-9`} aria-label="Search users" />
          </form>
          <select value={status} onChange={(e) => update({ status: e.target.value })} className={btn.input} aria-label="Status">
            <option value="">Any status</option>
            <option value="active">Active</option>
            <option value="suspended">Suspended</option>
          </select>
          <select value={role} onChange={(e) => update({ role: e.target.value })} className={btn.input} aria-label="Role">
            <option value="">Any role</option>
            <option value="user">Users</option>
            <option value="admin">Administrators</option>
          </select>
          <select value={verified} onChange={(e) => update({ verified: e.target.value })} className={btn.input} aria-label="Email verification">
            <option value="">Verified or not</option>
            <option value="true">Verified</option>
            <option value="false">Not verified</option>
          </select>
          <button onClick={() => setParams(new URLSearchParams())} disabled={!filtered} className={btn.secondary}>
            <RotateCcw size={15} /> Reset
          </button>
        </div>
        {users.loading && !d ? (
          <Spinner />
        ) : users.error ? (
          <ErrorBox message={users.error} onRetry={users.reload} />
        ) : !d?.items.length ? (
          <EmptyState title={filtered ? "No accounts match these filters" : "No accounts yet"} />
        ) : (
          <>
            <div className={`relative overflow-x-auto transition-opacity duration-200 ${users.loading ? "opacity-60" : ""}`}>
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead>
                  <tr className="bg-mint-50 text-xs font-semibold text-slate-600">
                    <th className="px-4 py-2.5">Name</th>
                    <th className="px-4 py-2.5">Email</th>
                    <th className="px-4 py-2.5">Role</th>
                    <th className="px-4 py-2.5">Status</th>
                    <th className="px-4 py-2.5">Verified</th>
                    <th className="px-4 py-2.5">Last sign-in</th>
                    <th className="px-4 py-2.5 text-right"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-leaf-100">
                  {d.items.map((u) => (
                    <tr key={u.id} className="cursor-pointer transition-colors hover:bg-mint-50/70" onClick={() => setSelected(u.id)}>
                      <td className="px-4 py-2.5">
                        <p className="font-medium">{u.full_name}</p>
                        <p className="text-xs text-slate-500">@{u.username}</p>
                      </td>
                      <td className="px-4 py-2.5 text-slate-600">{u.email ?? "—"}</td>
                      <td className="px-4 py-2.5"><RoleBadge role={u.role} /></td>
                      <td className="px-4 py-2.5"><StatusBadge u={u} /></td>
                      <td className="px-4 py-2.5 text-slate-600">{u.email_verified_at ? "Yes" : <span className="text-amber-700">No</span>}</td>
                      <td className="px-4 py-2.5 text-slate-600">{u.last_sign_in_at ? dateTime(u.last_sign_in_at) : "Never"}</td>
                      <td className="px-4 py-2.5 text-right">
                        <button onClick={(e) => { e.stopPropagation(); setSelected(u.id); }} className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-leaf-700 transition hover:bg-leaf-50">
                          <Eye size={14} /> View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-leaf-100 px-5 py-3 text-sm">
              <span className="text-slate-500">Page {d.page} of {d.pages}</span>
              <div className="flex gap-2">
                <button className={btn.secondary} disabled={page <= 1} onClick={() => update({ page: String(page - 1) })}><ChevronLeft size={16} /> Previous</button>
                <button className={btn.secondary} disabled={page >= d.pages} onClick={() => update({ page: String(page + 1) })}>Next <ChevronRight size={16} /></button>
              </div>
            </div>
          </>
        )}
      </Card>
      {selected && <UserDetail id={selected} onClose={() => setSelected(null)} onChanged={users.reload} />}
    </div>
  );
}
