import { FlaskConical, ShieldCheck } from "lucide-react";
import { pct } from "../lib/format";
import type { ModelInfo } from "../lib/types";
import { Card, CardHeader, EmptyState } from "./ui";

/** Offline evaluation of the trained model on the held-out test split (not live app data). */
export default function ModelMetrics({ info }: { info: ModelInfo }) {
  const ev = info.evaluation;
  return (
    <Card>
      <CardHeader icon={<FlaskConical size={19} />} title="Model Evaluation (independent test set)" />
      <p className="px-5 pt-1 text-xs text-slate-500">
        Offline results from <code>evaluate_model.py</code> on images never used for training or model selection. These are not live
        application statistics.
      </p>
      {!ev ? (
        <EmptyState title="No evaluation results yet">
          Run <code>python evaluate_model.py</code> in the backend folder.
        </EmptyState>
      ) : (
        <div className="grid gap-6 p-5 lg:grid-cols-[1.3fr_1fr]">
          <div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                ["Accuracy", pct(ev.test.accuracy)],
                ["Macro F1", pct(ev.test.macro_f1)],
                ["ROC AUC", ev.test.roc_auc?.toFixed(3) ?? "—"],
                ["Test images", String(ev.test.n)],
              ].map(([k, v]) => (
                <div key={k} className="rounded-xl bg-mint-50 p-3">
                  <p className="text-xs text-slate-500">{k}</p>
                  <p className="text-lg font-bold">{v}</p>
                </div>
              ))}
            </div>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[360px] text-sm">
                <thead>
                  <tr className="bg-mint-50 text-left text-xs text-slate-600">
                    <th className="px-3 py-2">Class</th>
                    <th className="px-3 py-2">Precision</th>
                    <th className="px-3 py-2">Recall</th>
                    <th className="px-3 py-2">F1-score</th>
                    <th className="px-3 py-2">Support</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-leaf-100 tabular-nums">
                  {(["Healthy", "Damaged"] as const).map((c) => (
                    <tr key={c}>
                      <td className="px-3 py-2 font-medium">{c}</td>
                      <td className="px-3 py-2">{pct(ev.test.per_class[c].precision)}</td>
                      <td className="px-3 py-2">{pct(ev.test.per_class[c].recall)}</td>
                      <td className="px-3 py-2">{pct(ev.test.per_class[c].f1)}</td>
                      <td className="px-3 py-2">{ev.test.per_class[c].support}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="mt-4 space-y-1 text-xs text-slate-600">
              <li>
                Accuracy — train (no augmentation) {pct(ev.train_no_augmentation.accuracy)} · validation {pct(ev.validation.accuracy)} · test{" "}
                {pct(ev.test.accuracy)}: <span className="font-medium">{ev.overfitting_check.assessment}</span>
              </li>
              {Object.entries(ev.test_by_background).map(([k, m]) => (
                <li key={k}>
                  Test photos with a {k} background: {m.n} images, accuracy {pct(m.accuracy)}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="mb-2 text-sm font-semibold">Confusion matrix</p>
            <table className="w-full max-w-xs text-center text-sm" aria-label="Confusion matrix: rows are actual, columns predicted">
              <thead>
                <tr className="text-xs text-slate-500">
                  <th />
                  <th className="pb-1">Pred. Damaged</th>
                  <th className="pb-1">Pred. Healthy</th>
                </tr>
              </thead>
              <tbody>
                {["Damaged", "Healthy"].map((actual, i) => (
                  <tr key={actual}>
                    <th className="pr-2 text-right text-xs font-normal text-slate-500">Actual {actual}</th>
                    {ev.test.confusion_matrix[i].map((v, j) => (
                      <td key={j} className="p-1">
                        <div className={`rounded-lg py-4 text-lg font-bold ${i === j ? "bg-leaf-600 text-white" : "bg-amber-50 text-amber-700"}`}>{v}</div>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 text-xs text-slate-500">
              Model {ev.model_version}. Green cells are correct predictions; amber cells are errors.
            </p>
          </div>
        </div>
      )}
    </Card>
  );
}

const CATEGORY_LABELS: Record<string, string> = {
  other_citrus_leaves: "Other citrus leaves (Citrus Leaves dataset)",
  other_citrus_leaves_plantvillage: "Other citrus leaves (PlantVillage orange)",
  citrus_fruits: "Citrus fruits",
  other_plant_leaves: "Other plant leaves (PlantVillage)",
  flowers: "Flowers",
  everyday_objects: "Everyday objects & animals (Imagenette)",
  caltech_objects: "Objects (Caltech-101)",
  people: "People (faces)",
  empty_backgrounds: "Blank photos / empty backgrounds",
  lemon_leaves: "Lemon leaves (2 Mendeley datasets)",
  orange_leaves_hlb: "Orange leaves (Mexico HLB dataset)",
  inat_other_citrus: "Real lemon, lime & orange plant photos (iNaturalist)",
};

/** Offline test results of the calamansi-leaf check that runs before classification. */
export function LeafCheckMetrics({ info }: { info: ModelInfo }) {
  const lc = info.leaf_check;
  if (!lc) return null;
  const acc = lc.calamansi_test_acceptance;
  return (
    <Card>
      <CardHeader icon={<ShieldCheck size={19} />} title="Calamansi-Leaf Check (held-out test images)" />
      <p className="px-5 pt-1 text-xs text-slate-500">
        Every upload is checked before classification; images that are not recognised as a calamansi leaf are rejected. "Never seen" = a
        separate test in which the check was retrained without that category, to show how it handles kinds of images it has never seen.
      </p>
      <div className="grid gap-6 p-5 lg:grid-cols-[1fr_1.6fr]">
        <div className="space-y-3">
          <div className="rounded-xl bg-leaf-50 p-3">
            <p className="text-xs text-slate-500">Calamansi test photos accepted</p>
            <p className="text-lg font-bold">{pct(acc.all_photos)}</p>
            <p className="text-xs text-slate-500">of {acc.n} photos</p>
          </div>
          <div className="rounded-xl bg-leaf-50 p-3">
            <p className="text-xs text-slate-500">Calamansi leaves on new backgrounds accepted</p>
            <p className="text-lg font-bold">{pct(acc.on_new_backgrounds)}</p>
            <p className="text-xs text-slate-500">of {acc.n_new_backgrounds} synthetic test images</p>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[380px] text-sm tabular-nums">
            <thead>
              <tr className="bg-mint-50 text-left text-xs text-slate-600">
                <th className="px-3 py-2">Not calamansi</th>
                <th className="px-3 py-2">Rejected</th>
                <th className="px-3 py-2">Rejected when never seen</th>
                <th className="px-3 py-2">Images</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-leaf-100">
              {Object.entries(lc.negative_test_rejection).map(([k, v]) => (
                <tr key={k}>
                  <td className="px-3 py-1.5">{CATEGORY_LABELS[k] ?? k}</td>
                  <td className="px-3 py-1.5 font-medium">{pct(v.rejected)}</td>
                  <td className="px-3 py-1.5">{pct(lc.unseen_experiment?.rejected_when_unseen[k]?.rejected)}</td>
                  <td className="px-3 py-1.5">{v.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Card>
  );
}
