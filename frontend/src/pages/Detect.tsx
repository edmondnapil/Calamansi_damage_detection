import { AlertTriangle, Leaf, ScanLine } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import Detector from "../components/Detector";
import { Card, CardHeader, ErrorBox } from "../components/ui";
import { api } from "../lib/api";
import { useAsync } from "../lib/useAsync";

export default function Detect() {
  const [params] = useSearchParams();
  const health = useAsync(() => api.health(), []);
  const h = health.data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Detect Calamansi Leaf</h1>
        <p className="mt-1 text-sm text-slate-600">
          Upload or capture a photo of a calamansi leaf. The trained model classifies it as <strong>Healthy</strong> or{" "}
          <strong>Damaged</strong> and the result is saved to the detection log.
        </p>
      </div>

      {health.error && <ErrorBox message={health.error} onRetry={health.reload} />}
      {h && !h.model.loaded && (
        <ErrorBox message={`The classification model is not loaded, so predictions are unavailable. ${h.model.error ?? ""}`} onRetry={health.reload} />
      )}
      {h && !h.database.connected && <ErrorBox message={`Database unavailable: ${h.database.error ?? "unknown error"}. Results cannot be saved.`} />}

      <Card>
        <CardHeader icon={<ScanLine size={19} />} title="Classify a leaf" />
        <div className="p-5">
          <Detector maxMb={h?.max_upload_mb ?? 5} openCamera={params.get("camera") === "1"} />
        </div>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="flex gap-4 p-5">
          <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-leaf-600 text-white">
            <Leaf size={19} />
          </span>
          <div className="text-sm text-slate-600">
            <p className="font-semibold text-forest-950">What the model can do</p>
            First check that the photo shows a calamansi leaf, then classify it as healthy-looking or damaged-looking, based on patterns learned
            from the project's calamansi leaf dataset.
          </div>
        </Card>
        <Card className="flex gap-4 p-5">
          <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-amber-500 text-white">
            <AlertTriangle size={19} />
          </span>
          <div className="text-sm text-slate-600">
            <p className="font-semibold text-forest-950">Limitations</p>
            Photos that are not recognised as a calamansi leaf (other plants, fruit, people, objects) are rejected instead of classified. It
            does not name diseases or pests, and very similar leaves (e.g. other citrus) can occasionally pass the check. Treat results as an
            aid, not a diagnosis.
          </div>
        </Card>
      </div>
    </div>
  );
}
