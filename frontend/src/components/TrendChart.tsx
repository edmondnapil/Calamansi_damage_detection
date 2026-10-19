import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipProps } from "recharts";
import { shortDate } from "../lib/format";
import type { DailyPoint } from "../lib/types";

export const SERIES = [
  { key: "Healthy", color: "#1f8a4c" },
  { key: "Damaged", color: "#e0a106" },
] as const;

export function Legend() {
  return (
    <div className="flex items-center gap-5 text-sm text-slate-600">
      {SERIES.map((s) => (
        <span key={s.key} className="inline-flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: s.color }} />
          {s.key}
        </span>
      ))}
    </div>
  );
}

function ChartTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  const total = payload.reduce((s, p) => s + (p.value ?? 0), 0);
  return (
    <div className="rounded-xl border border-leaf-100 bg-white px-3 py-2 text-xs shadow-card">
      <p className="mb-1 font-semibold text-forest-950">{shortDate(String(label))}</p>
      {payload.map((p) => (
        <p key={p.dataKey as string} className="flex items-center gap-2 text-slate-600">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
          {p.dataKey}: <span className="ml-auto font-semibold text-forest-950">{p.value}</span>
        </p>
      ))}
      <p className="mt-1 border-t border-leaf-100 pt-1 text-slate-500">Total: {total}</p>
    </div>
  );
}

/** Daily Healthy vs Damaged detection counts (single y-axis, two series). */
export default function TrendChart({ data, height = 240 }: { data: DailyPoint[]; height?: number }) {
  const many = data.length > 14;
  return (
    <div style={{ height }} role="img" aria-label="Daily Healthy and Damaged detections chart">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 10, right: 24, left: -18, bottom: 0 }}>
          <defs>
            {SERIES.map((s) => (
              <linearGradient key={s.key} id={`fill-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.color} stopOpacity={0.18} />
                <stop offset="100%" stopColor={s.color} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid stroke="#e8f1ea" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={shortDate}
            tick={{ fontSize: 11, fill: "#64748b" }}
            axisLine={{ stroke: "#d7e7dc" }}
            tickLine={false}
            interval={many ? "preserveStartEnd" : 0}
            minTickGap={12}
          />
          <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} />
          <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#9cc9aa", strokeDasharray: "3 3" }} />
          {SERIES.map((s) => (
            <Area
              key={s.key}
              type="monotone"
              dataKey={s.key}
              stroke={s.color}
              strokeWidth={2}
              fill={`url(#fill-${s.key})`}
              dot={many ? false : { r: 4, strokeWidth: 2, stroke: "#fff", fill: s.color }}
              activeDot={{ r: 5, strokeWidth: 2, stroke: "#fff" }}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
