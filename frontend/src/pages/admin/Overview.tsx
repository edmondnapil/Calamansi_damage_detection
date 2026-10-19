import { Activity, AlertTriangle, ArrowRight, BarChart3, CalendarDays, Leaf, MailWarning, ShieldCheck, UserCheck, UserPlus, Users, UserX } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Link } from "react-router-dom";
import TrendChart, { Legend } from "../../components/TrendChart";
import { Card, CardHeader, EmptyState, ErrorBox, SectionLabel, Spinner, StatCard } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { dateTime, shortDate } from "../../lib/format";
import { useAsync } from "../../lib/useAsync";
import { eventLabel, StatusPill } from "./Activity";

function RegistrationsChart({ data }: { data: { date: string; count: number }[] }) {
  return (
    <div style={{ height: 220 }} role="img" aria-label="New registrations per day">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 16, left: -22, bottom: 0 }}>
          <CartesianGrid stroke="#e8f1ea" vertical={false} />
          <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 11, fill: "#64748b" }} axisLine={{ stroke: "#d7e7dc" }} tickLine={false} minTickGap={14} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} />
          <Tooltip
            cursor={{ fill: "rgba(31,138,76,0.06)" }}
            labelFormatter={(l) => shortDate(String(l))}
            formatter={(v) => [v as number, "New accounts"]}
            contentStyle={{ borderRadius: 12, border: "1px solid #e1f0e6", fontSize: 12 }}
          />
          <Bar dataKey="count" fill="#1f8a4c" radius={[4, 4, 0, 0]} maxBarSize={28} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function AdminOverview() {
  const { user } = useAuth();
  const [days, setDays] = useState(14);
  const ov = useAsync(() => api.adminOverview(days), [days]);
  const d = ov.data;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-leaf-700">Administrator dashboard</p>
          <h1 className="text-2xl font-bold">Welcome, {user?.full_name?.split(" ")[0] ?? "Administrator"}</h1>
          <p className="mt-1 text-sm text-slate-600">Live figures from the database: accounts, detections and security activity.</p>
        </div>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="rounded-xl border border-leaf-100 bg-white px-3 py-2 text-sm transition focus:border-leaf-500 focus:outline-none focus:ring-4 focus:ring-leaf-100" aria-label="Chart period">
          {[7, 14, 30, 90].map((n) => (
            <option key={n} value={n}>Last {n} days</option>
          ))}
        </select>
      </div>

      {ov.error ? (
        <Card><ErrorBox message={ov.error} onRetry={ov.reload} /></Card>
      ) : !d ? (
        <Spinner label="Loading dashboard…" />
      ) : (
        <>
          <section className="space-y-3">
            <SectionLabel action={<Link to="/admin/users" className="inline-flex items-center gap-1 text-sm font-semibold text-leaf-700 hover:underline">Manage users <ArrowRight size={15} /></Link>}>
              Accounts
            </SectionLabel>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard icon={<Users size={18} />} tone="forest" label="Registered users" value={d.users.total} sub={`${d.users.admins} administrator${d.users.admins === 1 ? "" : "s"} · ${d.users.new_last_7_days} new this week`} />
              <StatCard icon={<UserCheck size={18} />} tone="green" label="Active accounts" value={d.users.active} sub={`${d.users.signed_in_last_7_days} signed in during the last 7 days`} />
              <StatCard icon={<MailWarning size={18} />} tone="amber" label="Unverified emails" value={d.users.unverified} sub={`${d.users.verified} verified`} />
              <StatCard icon={<UserX size={18} />} tone="red" label="Suspended accounts" value={d.users.suspended} sub={d.users.suspended ? "Cannot sign in" : "None"} />
            </div>
          </section>

          <section className="space-y-3">
            <SectionLabel>Detections · all users</SectionLabel>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard icon={<BarChart3 size={18} />} tone="forest" label="Total detections" value={d.detections.total} sub="All time" />
              <StatCard icon={<CalendarDays size={18} />} tone="slate" label={`Last ${d.days} days`} value={d.detections.in_period} sub="Detections in the selected period" />
              <StatCard icon={<Leaf size={18} />} tone="green" label="Healthy results" value={d.detections.healthy} sub={`${d.detections.total ? Math.round((d.detections.healthy / d.detections.total) * 100) : 0}% of all results`} />
              <StatCard icon={<AlertTriangle size={18} />} tone="amber" label="Damaged results" value={d.detections.damaged} sub={`${d.detections.total ? Math.round((d.detections.damaged / d.detections.total) * 100) : 0}% of all results`} />
            </div>
          </section>

          <SectionLabel>Trends · last {d.days} days</SectionLabel>
          <div className="grid gap-6 xl:grid-cols-2 [&>*]:min-w-0">
            <Card>
              <CardHeader icon={<UserPlus size={19} />} title="New registrations per day" />
              <div className="px-3 pb-4 pt-3">
                {d.registrations_daily.some((x) => x.count) ? <RegistrationsChart data={d.registrations_daily} /> : <EmptyState title={`No registrations in the last ${d.days} days`} />}
              </div>
            </Card>
            <Card>
              <CardHeader icon={<BarChart3 size={19} />} title="Detections per day (all users)" action={<Legend />} />
              <div className="px-3 pb-4 pt-3">
                {d.detections.in_period ? <TrendChart data={d.detections_daily} height={220} /> : <EmptyState title={`No detections in the last ${d.days} days`} />}
              </div>
            </Card>
          </div>

          <SectionLabel>Latest activity</SectionLabel>
          <div className="grid gap-6 xl:grid-cols-2 [&>*]:min-w-0">
            <Card>
              <CardHeader
                icon={<UserPlus size={19} />}
                title="Recent registrations"
                action={<Link to="/admin/users" className="inline-flex items-center gap-1 text-sm font-semibold text-leaf-700 hover:underline">All users <ArrowRight size={15} /></Link>}
              />
              <ul className="divide-y divide-leaf-100 px-5 pb-3 pt-2">
                {d.recent_registrations.length ? (
                  d.recent_registrations.map((u) => (
                    <li key={u.id} className="flex items-center gap-3 py-3">
                      <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-mint-100 text-sm font-semibold text-forest-800">{u.full_name.charAt(0).toUpperCase()}</span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">{u.full_name} {u.role === "admin" && <ShieldCheck size={13} className="inline text-leaf-700" />}</p>
                        <p className="truncate text-xs text-slate-500">{u.email}</p>
                      </div>
                      <div className="text-right text-xs text-slate-500">
                        <p>{dateTime(u.created_at)}</p>
                        <p className={u.email_verified_at ? "text-leaf-700" : "text-amber-700"}>{u.email_verified_at ? "Verified" : "Not verified"}</p>
                      </div>
                    </li>
                  ))
                ) : (
                  <EmptyState title="No accounts yet" />
                )}
              </ul>
            </Card>
            <Card>
              <CardHeader
                icon={<Activity size={19} />}
                title="Recent security activity"
                action={<Link to="/admin/activity" className="inline-flex items-center gap-1 text-sm font-semibold text-leaf-700 hover:underline">Full log <ArrowRight size={15} /></Link>}
              />
              <ul className="divide-y divide-leaf-100 px-5 pb-3 pt-2">
                {d.recent_activity.length ? (
                  d.recent_activity.map((a, i) => (
                    <li key={i} className="flex items-center gap-3 py-2.5 text-sm">
                      <StatusPill status={a.event_status} />
                      <span className="min-w-0 flex-1 truncate">{eventLabel(a.event_type)}{a.user_name ? <span className="text-slate-500"> · {a.user_name}</span> : null}</span>
                      <span className="shrink-0 text-xs text-slate-500">{dateTime(a.created_at)}</span>
                    </li>
                  ))
                ) : (
                  <EmptyState title="No activity yet" />
                )}
              </ul>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
