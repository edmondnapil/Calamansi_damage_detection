import { ChevronLeft, ChevronRight, FileText, RotateCcw, Search } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import DetectionTable from "../components/DetectionTable";
import { btn, Card, CardHeader, EmptyState, ErrorBox, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { loadPrefs } from "../lib/format";
import { useAsync } from "../lib/useAsync";

export default function Logs() {
  const [params, setParams] = useSearchParams();
  const search = params.get("search") ?? "";
  const cls = params.get("class") ?? "";
  const from = params.get("from") ?? "";
  const to = params.get("to") ?? "";
  const page = Number(params.get("page") ?? "1") || 1;
  const pageSize = loadPrefs().pageSize;
  const [draft, setDraft] = useState(search);
  useEffect(() => {
    setDraft(search);
  }, [search]);

  const data = useAsync(
    () => api.detections({ search, predicted_class: cls, date_from: from, date_to: to, page, page_size: pageSize }),
    [search, cls, from, to, page, pageSize],
  );

  const update = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    if (!("page" in patch)) next.delete("page");
    setParams(next);
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    update({ search: draft.trim() });
  };
  const filtered = !!(search || cls || from || to);
  const d = data.data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Detection Logs</h1>
        <p className="mt-1 text-sm text-slate-600">Every classification made by the model, newest first.</p>
      </div>

      <Card>
        <CardHeader icon={<FileText size={19} />} title="All detections" action={d && <span className="text-sm text-slate-500">{d.total} records</span>} />
        <div className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr_auto]">
          <form onSubmit={submit} className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={() => draft.trim() !== search && update({ search: draft.trim() })}
              placeholder="Search file name, result, model…"
              className={`${btn.input} pl-9`}
              aria-label="Search"
            />
          </form>
          <select value={cls} onChange={(e) => update({ class: e.target.value })} className={btn.input} aria-label="Classification">
            <option value="">All results</option>
            <option value="Healthy">Healthy</option>
            <option value="Damaged">Damaged</option>
          </select>
          <label className="flex items-center gap-2 text-xs text-slate-500">
            From
            <input type="date" value={from} max={to || undefined} onChange={(e) => update({ from: e.target.value })} className={btn.input} />
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-500">
            To
            <input type="date" value={to} min={from || undefined} onChange={(e) => update({ to: e.target.value })} className={btn.input} />
          </label>
          <button onClick={() => setParams(new URLSearchParams())} disabled={!filtered} className={btn.secondary}>
            <RotateCcw size={15} /> Reset
          </button>
        </div>

        {data.loading && !d ? (
          <Spinner />
        ) : data.error ? (
          <ErrorBox message={data.error} onRetry={data.reload} />
        ) : d && d.items.length ? (
          <>
            <div className={data.loading ? "opacity-60" : ""}>
              <DetectionTable items={d.items} />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-leaf-100 px-5 py-3 text-sm">
              <span className="text-slate-500">
                Page {d.page} of {d.pages} · showing {(d.page - 1) * d.page_size + 1}–{Math.min(d.page * d.page_size, d.total)} of {d.total}
              </span>
              <div className="flex gap-2">
                <button className={btn.secondary} disabled={page <= 1} onClick={() => update({ page: String(page - 1) })}>
                  <ChevronLeft size={16} /> Previous
                </button>
                <button className={btn.secondary} disabled={page >= d.pages} onClick={() => update({ page: String(page + 1) })}>
                  Next <ChevronRight size={16} />
                </button>
              </div>
            </div>
          </>
        ) : (
          <EmptyState title={filtered ? "No detections match these filters" : "No detections yet"}>
            {filtered ? (
              "Try a different search term or date range."
            ) : (
              <>
                <Link to="/app/detect" className="font-semibold text-leaf-700 hover:underline">
                  Classify your first leaf
                </Link>{" "}
                to start the log.
              </>
            )}
          </EmptyState>
        )}
      </Card>
    </div>
  );
}
