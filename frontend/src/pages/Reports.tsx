import { AlertTriangle, BarChart3, Download, Gauge, Image as ImageIcon, Leaf } from "lucide-react";
import { useState, type ReactNode } from "react";
import ModelMetrics from "../components/ModelMetrics";
import TrendChart, { Legend } from "../components/TrendChart";
import { btn, Card, CardHeader, EmptyState, ErrorBox, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { daysAgo, isoDay, pct, shortDate } from "../lib/format";
import { useAsync } from "../lib/useAsync";

const PRESETS = [
  { label: "7 days", days: 7 },
  { label: "30 days", days: 30 },
  { label: "90 days", days: 90 },
];

function Tile({ icon, label, value, sub, tone }: { icon: ReactNode; label: string; value: string | number; sub?: string; tone: string }) {
  return (
    <Card className="flex items-center gap-4 p-5">
      <span className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-white ${tone}`}>{icon}</span>
      <div>
        <p className="text-sm text-slate-500">{label}</p>
        <p className="text-2xl font-bold">{value}</p>
        {sub && <p className="text-xs text-slate-500">{sub}</p>}
      </div>
    </Card>
  );
}

export default function Reports() {
  const [from, setFrom] = useState(daysAgo(29));
  const [to, setTo] = useState(isoDay(new Date()));
  const report = useAsync(() => api.reports(from, to), [from, to]);
  const model = useAsync(() => api.model(), []);
  const r = report.data;
  const share = (n: number) => (r && r.total ? ` · ${((n / r.total) * 100).toFixed(1)}% of period` : "");

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Reports</h1>
          <p className="mt-1 text-sm text-slate-600">Live statistics from saved detection records.</p>
        </div>
        <a href={api.exportUrl(from, to)} className={btn.secondary} download>
          <Download size={16} /> Export CSV
        </a>
      </div>

      <Card className="flex flex-wrap items-center gap-3 p-4">
        <span className="text-sm font-medium text-slate-600">Period:</span>
        {PRESETS.map((p) => {
          const active = from === daysAgo(p.days - 1) && to === isoDay(new Date());
          return (
            <button
              key={p.days}
              onClick={() => {
                setFrom(daysAgo(p.days - 1));
                setTo(isoDay(new Date()));
              }}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium ${active ? "bg-forest-800 text-white" : "bg-mint-100 text-forest-800 hover:bg-leaf-100"}`}
            >
              Last {p.label}
            </button>
          );
        })}
        <div className="flex flex-wrap items-center gap-2 sm:ml-auto">
          <input type="date" value={from} max={to} onChange={(e) => e.target.value && setFrom(e.target.value)} className={`${btn.input} !w-40`} aria-label="From date" />
          <span className="text-slate-400">to</span>
          <input type="date" value={to} min={from} onChange={(e) => e.target.value && setTo(e.target.value)} className={`${btn.input} !w-40`} aria-label="To date" />
        </div>
      </Card>

      {report.error ? (
        <Card>
          <ErrorBox message={report.error} onRetry={report.reload} />
        </Card>
      ) : !r ? (
        <Spinner />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Tile icon={<ImageIcon size={20} />} tone="bg-forest-700" label="Total detections" value={r.total} sub={`${shortDate(r.date_from)} – ${shortDate(r.date_to)}`} />
            <Tile icon={<Leaf size={20} />} tone="bg-leaf-600" label="Healthy" value={r.counts.Healthy} sub={`avg. confidence ${pct(r.average_confidence.Healthy)}${share(r.counts.Healthy)}`} />
            <Tile icon={<AlertTriangle size={20} />} tone="bg-amber-500" label="Damaged" value={r.counts.Damaged} sub={`avg. confidence ${pct(r.average_confidence.Damaged)}${share(r.counts.Damaged)}`} />
            <Tile icon={<Gauge size={20} />} tone="bg-slate-500" label="Low-confidence results" value={r.low_confidence_count} sub="confidence below 70%" />
          </div>

          <Card>
            <CardHeader icon={<BarChart3 size={19} />} title="Detections per day" action={<Legend />} />
            <div className={`px-3 pb-4 pt-3 ${report.loading ? "opacity-60" : ""}`}>
              {r.total === 0 ? <EmptyState title="No detections in this period" /> : <TrendChart data={r.daily} height={300} />}
            </div>
            {r.total > 0 && (
              <details className="border-t border-leaf-100 px-5 py-3 text-sm">
                <summary className="cursor-pointer font-medium text-leaf-700">Show data table</summary>
                <div className="mt-3 max-h-72 overflow-auto">
                  <table className="w-full text-sm tabular-nums">
                    <thead>
                      <tr className="bg-mint-50 text-left text-xs text-slate-600">
                        <th className="px-3 py-2">Date</th>
                        <th className="px-3 py-2">Healthy</th>
                        <th className="px-3 py-2">Damaged</th>
                        <th className="px-3 py-2">Total</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-leaf-100">
                      {r.daily.filter((d) => d.Healthy + d.Damaged > 0).map((d) => (
                        <tr key={d.date}>
                          <td className="px-3 py-1.5">{d.date}</td>
                          <td className="px-3 py-1.5">{d.Healthy}</td>
                          <td className="px-3 py-1.5">{d.Damaged}</td>
                          <td className="px-3 py-1.5 font-medium">{d.Healthy + d.Damaged}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}
          </Card>
        </>
      )}

      {model.error ? <ErrorBox message={model.error} onRetry={model.reload} /> : model.data ? <ModelMetrics info={model.data} /> : <Spinner />}
    </div>
  );
}
