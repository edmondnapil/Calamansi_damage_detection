import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Card, ErrorBox, ResultBadge, Spinner, StatusIcon } from "../components/ui";
import { api, imageSrc } from "../lib/api";
import { dateTime, pct } from "../lib/format";
import { useAsync } from "../lib/useAsync";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-3 border-b border-leaf-100 py-2.5 text-sm last:border-0">
      <dt className="text-slate-500">{label}</dt>
      <dd className="min-w-0 break-words font-medium text-forest-950">{children}</dd>
    </div>
  );
}

export default function DetectionDetail() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const q = useAsync(() => api.detection(id), [id]);
  const d = q.data;

  return (
    <div className="space-y-6">
      <button onClick={() => (window.history.length > 1 ? navigate(-1) : navigate("/app/logs"))} className="inline-flex items-center gap-1.5 text-sm font-semibold text-leaf-700 hover:underline">
        <ArrowLeft size={16} /> Back
      </button>
      {q.loading ? (
        <Spinner />
      ) : q.error ? (
        <Card>
          <ErrorBox message={q.error} onRetry={q.reload} />
          <p className="px-5 pb-5 text-sm">
            <Link to="/app/logs" className="font-semibold text-leaf-700 hover:underline">
              Go to all logs
            </Link>
          </p>
        </Card>
      ) : (
        d && (
          <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
            <Card className="p-4">
              {d.image_url ? (
                <img src={imageSrc(d.image_url)} alt={`${d.predicted_class} calamansi leaf`} className="max-h-[520px] w-full rounded-xl object-contain" />
              ) : (
                <div className="flex h-72 items-center justify-center rounded-xl bg-mint-100 text-sm text-slate-500">
                  The image was not retained for this detection.
                </div>
              )}
            </Card>
            <Card className="p-5">
              <div className="mb-4 flex items-center gap-4">
                <StatusIcon value={d.predicted_class} size={52} />
                <div>
                  <h1 className={`text-2xl font-bold ${d.predicted_class === "Healthy" ? "text-leaf-700" : "text-amber-700"}`}>
                    {d.predicted_class} Leaf
                  </h1>
                  <p className="text-sm text-slate-500">Confidence {pct(d.confidence)}</p>
                </div>
              </div>
              <dl>
                <Row label="Result">
                  <ResultBadge value={d.predicted_class} />
                </Row>
                <Row label="Confidence">{pct(d.confidence, 2)}</Row>
                <Row label="P(Healthy)">{pct(d.prob_healthy, 2)}</Row>
                <Row label="P(Damaged)">{pct(d.prob_damaged, 2)}</Row>
                <Row label="Date & time">{dateTime(d.created_at)}</Row>
                <Row label="File name">{d.original_filename ?? "—"}</Row>
                <Row label="Model version">{d.model_version}</Row>
                <Row label="Record ID">
                  <span className="font-mono text-xs">{d.id}</span>
                </Row>
              </dl>
              <p className="mt-4 rounded-xl bg-mint-50 p-3 text-xs text-slate-600">
                Confidence is the model's estimated probability for Healthy vs. Damaged. It is not a measure of whether the leaf is calamansi
                (a separate check decides that before classification), not a guarantee of correctness, and not a professional plant-health
                diagnosis.
              </p>
            </Card>
          </div>
        )
      )}
    </div>
  );
}
