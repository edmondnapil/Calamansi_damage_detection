import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";
import { imageSrc } from "../lib/api";
import { dateTime, pct } from "../lib/format";
import type { Detection } from "../lib/types";
import { ResultBadge, Thumb } from "./ui";

export default function DetectionTable({ items, compact = false }: { items: Detection[]; compact?: boolean }) {
  return (
    <div className="relative overflow-x-auto">
      <table className="w-full min-w-[520px] text-left text-sm">
        <thead>
          <tr className="bg-mint-50 text-xs font-semibold text-slate-600">
            <th className="px-4 py-2.5">Date &amp; Time</th>
            <th className="px-4 py-2.5">Image</th>
            {!compact && <th className="px-4 py-2.5">File name</th>}
            <th className="px-4 py-2.5">Result</th>
            <th className="px-4 py-2.5">Confidence</th>
            <th className="px-4 py-2.5 text-right">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-leaf-100">
          {items.map((d) => (
            <tr key={d.id} className="hover:bg-mint-50/60">
              <td className="whitespace-nowrap px-4 py-2.5 text-slate-700">{dateTime(d.created_at)}</td>
              <td className="px-4 py-2">
                <Thumb src={imageSrc(d.image_url)} alt={`${d.predicted_class} leaf`} size={compact ? 32 : 40} />
              </td>
              {!compact && (
                <td className="max-w-[220px] truncate px-4 py-2.5 text-slate-600" title={d.original_filename ?? ""}>
                  {d.original_filename ?? "—"}
                </td>
              )}
              <td className="px-4 py-2.5">
                <ResultBadge value={d.predicted_class} />
              </td>
              <td className="px-4 py-2.5 font-medium tabular-nums text-forest-950">{pct(d.confidence)}</td>
              <td className="px-4 py-2.5 text-right">
                <Link
                  to={`/app/logs/${d.id}`}
                  className="inline-flex items-center gap-0.5 whitespace-nowrap text-xs font-semibold text-leaf-700 hover:underline"
                >
                  View <ChevronRight size={14} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
