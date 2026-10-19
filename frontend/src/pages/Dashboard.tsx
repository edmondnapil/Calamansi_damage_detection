import { AlertTriangle, ArrowRight, BarChart3, Camera, CloudUpload, Eye, FileText, Image as ImageIcon, Info, Leaf, PieChart, ScanLine } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import foliagePhoto from "../assets/calamansi-foliage.webp";
import DetectionTable from "../components/DetectionTable";
import TrendChart, { Legend } from "../components/TrendChart";
import { btn, Card, CardHeader, EmptyState, ErrorBox, SectionLabel, Spinner, StatCard, StatusIcon } from "../components/ui";
import { api, imageSrc } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dateTime, daysAgo, isoDay, loadPrefs, pct } from "../lib/format";
import type { Stats } from "../lib/types";
import { useAsync } from "../lib/useAsync";

const RANGES = [7, 14, 30];

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

/** Slim welcome strip with the two ways to start a detection. */
function Welcome() {
  const { user } = useAuth();
  const first = user?.full_name?.split(" ")[0];
  return (
    <section className="relative overflow-hidden rounded-2xl bg-forest-900 text-white shadow-card">
      <div className="relative z-10 flex flex-col gap-5 p-6 sm:p-7 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0 md:max-w-[60%]">
          <p className="text-sm font-medium text-lime-300">{greeting()}{first ? `, ${first}` : ""}</p>
          <h1 className="mt-1 text-2xl font-bold leading-tight sm:text-[28px]">Calamansi Leaf Damage Detection</h1>
          <p className="mt-2 text-sm text-white/75">Check a leaf photo for damage. Results are saved to your history below.</p>
        </div>
        <div className="flex flex-wrap gap-2.5">
          <Link to="/app/detect" className="inline-flex items-center gap-2 rounded-xl bg-leaf-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-leaf-500">
            <CloudUpload size={17} /> Upload leaf photo
          </Link>
          <Link to="/app/detect?camera=1" className="inline-flex items-center gap-2 rounded-xl bg-white/10 px-4 py-2.5 text-sm font-semibold text-white ring-1 ring-white/20 transition hover:bg-white/15">
            <Camera size={17} /> Take a photo
          </Link>
        </div>
      </div>
      <div className="pointer-events-none absolute inset-y-0 right-0 w-full md:w-[55%]" aria-hidden="true">
        <img src={foliagePhoto} alt="" className="h-full w-full object-cover opacity-60 md:opacity-100" />
        {/* fades the photo into the banner colour so the text stays readable */}
        <div className="absolute inset-0 bg-gradient-to-r from-forest-900 via-forest-900/80 to-forest-900/40" />
      </div>
    </section>
  );
}

function Figures({ stats, days }: { stats: ReturnType<typeof useAsync<Stats>>; days: number }) {
  const s = stats.data;
  if (stats.error) return <Card><ErrorBox message={stats.error} onRetry={stats.reload} /></Card>;
  const caption = `vs. previous ${days} days`;
  const share = s && s.total.period ? s.healthy.period / s.total.period : null;
  const v = (n?: number) => (n === undefined ? "–" : n);
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard icon={<ImageIcon size={18} />} tone="forest" label="Detections" value={v(s?.total.period)} change={s?.total.change_pct} caption={caption} sub={s && `All time: ${s.total.total}`} />
      <StatCard icon={<Leaf size={18} />} tone="green" label="Healthy leaves" value={v(s?.healthy.period)} change={s?.healthy.change_pct} caption={caption} sub={s && `All time: ${s.healthy.total}`} />
      <StatCard icon={<AlertTriangle size={18} />} tone="amber" label="Damaged leaves" value={v(s?.damaged.period)} change={s?.damaged.change_pct} caption={caption} sub={s && `All time: ${s.damaged.total}`} />
      <StatCard icon={<PieChart size={18} />} tone="green" label="Healthy share" value={share === null ? "–" : pct(share)}
        sub={s ? (share === null ? `No detections in the last ${days} days` : `${s.healthy.period} of ${s.total.period} leaves were healthy`) : undefined} />
    </div>
  );
}

function LatestDetection({ stats }: { stats: ReturnType<typeof useAsync<Stats>> }) {
  const d = stats.data?.latest;
  return (
    <Card className="flex h-full flex-col">
      <CardHeader icon={<ScanLine size={19} />} title="Latest detection" />
      {stats.error ? (
        <ErrorBox message={stats.error} onRetry={stats.reload} />
      ) : stats.loading && !stats.data ? (
        <Spinner />
      ) : !d ? (
        <EmptyState title="No detections yet">Upload a leaf photo to see its result here.</EmptyState>
      ) : (
        <div className="flex flex-1 flex-col gap-4 p-5">
          {d.image_url ? (
            <img src={imageSrc(d.image_url)} alt={`Latest ${d.predicted_class} leaf`} className="aspect-[4/3] w-full rounded-xl object-cover" />
          ) : (
            <div className="flex aspect-[4/3] items-center justify-center rounded-xl bg-mint-100 text-sm text-slate-500">Image not retained</div>
          )}
          <div className="flex items-center gap-3">
            <StatusIcon value={d.predicted_class} size={40} />
            <div className="min-w-0">
              <p className={`text-lg font-bold ${d.predicted_class === "Healthy" ? "text-leaf-700" : "text-amber-700"}`}>{d.predicted_class} leaf</p>
              <p className="truncate text-xs text-slate-500">
                Confidence {pct(d.confidence)} · {dateTime(d.created_at)}
              </p>
            </div>
          </div>
          <Link to={`/app/logs/${d.id}`} className={`${btn.secondary} mt-auto`}>
            <Eye size={16} /> View details
          </Link>
        </div>
      )}
    </Card>
  );
}

function Trend({ days }: { days: number }) {
  const report = useAsync(() => api.reports(daysAgo(days - 1), isoDay(new Date())), [days]);
  return (
    <Card className="flex h-full flex-col">
      <CardHeader icon={<BarChart3 size={19} />} title={`Detections per day · last ${days} days`} action={<Legend />} />
      <div className="flex-1 px-3 pb-4 pt-3">
        {report.loading && !report.data ? (
          <Spinner />
        ) : report.error ? (
          <ErrorBox message={report.error} onRetry={report.reload} />
        ) : report.data && report.data.total === 0 ? (
          <EmptyState title={`No detections in the last ${days} days`} />
        ) : (
          report.data && <TrendChart data={report.data.daily} height={280} />
        )}
      </div>
    </Card>
  );
}

function RecentLogs() {
  const recent = useAsync(() => api.detections({ page: 1, page_size: 5 }), []);
  return (
    <Card className="h-full">
      <CardHeader
        icon={<FileText size={19} />}
        title="Recent detections"
        action={
          <Link to="/app/logs" className="inline-flex items-center gap-1 text-sm font-semibold text-leaf-700 hover:underline">
            View all <ArrowRight size={15} />
          </Link>
        }
      />
      <div className="pb-2 pt-3">
        {recent.loading ? (
          <Spinner />
        ) : recent.error ? (
          <ErrorBox message={recent.error} onRetry={recent.reload} />
        ) : recent.data?.items.length ? (
          <DetectionTable items={recent.data.items} compact />
        ) : (
          <EmptyState title="No detections yet" />
        )}
      </div>
    </Card>
  );
}

/** Healthy vs. damaged split of the selected period, plus what the result means. */
function ResultSplit({ stats, days }: { stats: ReturnType<typeof useAsync<Stats>>; days: number }) {
  const s = stats.data;
  const total = s?.total.period ?? 0;
  const h = total ? (s!.healthy.period / total) * 100 : 0;
  return (
    <Card className="flex h-full flex-col">
      <CardHeader icon={<PieChart size={19} />} title="Result split" />
      <div className="flex flex-1 flex-col p-5">
        {!s ? (
          <Spinner />
        ) : !total ? (
          <p className="text-sm text-slate-500">No detections in the last {days} days.</p>
        ) : (
          <>
            <div className="flex h-3 overflow-hidden rounded-full bg-amber-100" role="img" aria-label={`${Math.round(h)}% healthy, ${100 - Math.round(h)}% damaged`}>
              <div className="h-full bg-leaf-600 transition-all duration-500 ease-smooth" style={{ width: `${h}%` }} />
              <div className="h-full flex-1 bg-amber-500" />
            </div>
            <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-xl bg-leaf-50 p-3">
                <dt className="flex items-center gap-1.5 text-xs text-slate-500"><span className="h-2 w-2 rounded-full bg-leaf-600" /> Healthy</dt>
                <dd className="mt-1 text-lg font-bold text-leaf-700">{s.healthy.period}</dd>
              </div>
              <div className="rounded-xl bg-amber-50 p-3">
                <dt className="flex items-center gap-1.5 text-xs text-slate-500"><span className="h-2 w-2 rounded-full bg-amber-500" /> Damaged</dt>
                <dd className="mt-1 text-lg font-bold text-amber-700">{s.damaged.period}</dd>
              </div>
            </dl>
          </>
        )}
        <p className="mt-5 flex gap-2 rounded-xl border border-leaf-100 bg-mint-50 p-3 text-xs leading-relaxed text-slate-600">
          <Info size={15} className="mt-0.5 shrink-0 text-leaf-700" />
          Results are limited to Healthy or Damaged. The system does not diagnose specific diseases.
        </p>
        <Link to="/app/reports" className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-leaf-700 hover:underline">
          Reports &amp; export <ArrowRight size={15} />
        </Link>
      </div>
    </Card>
  );
}

export default function Dashboard() {
  const [days, setDays] = useState(loadPrefs().chartDays);
  const stats = useAsync(() => api.stats(days), [days]);

  return (
    <div className="space-y-6">
      <Welcome />

      <section className="space-y-3">
        <SectionLabel
          action={
            <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="rounded-lg border border-leaf-100 bg-white px-2.5 py-1.5 text-sm" aria-label="Period">
              {RANGES.map((r) => (
                <option key={r} value={r}>
                  Last {r} days
                </option>
              ))}
            </select>
          }
        >
          Your results · last {days} days
        </SectionLabel>
        <Figures stats={stats} days={days} />
      </section>

      <div className="grid gap-6 lg:grid-cols-3 [&>*]:min-w-0">
        <div className="lg:col-span-2">
          <Trend days={days} />
        </div>
        <LatestDetection stats={stats} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3 [&>*]:min-w-0">
        <div className="lg:col-span-2">
          <RecentLogs />
        </div>
        <ResultSplit stats={stats} days={days} />
      </div>
    </div>
  );
}
