// Разложение оценок по клику: вклад компонент в новизну/риск/ценность
// и вклад признаков в итоговый ранг — интерпретируемость числа.

import type { Hypothesis, MetricBreakdown as MB } from "../types";

function Bar({ label, value }: { label: string; value: number }) {
  const pct = Math.max(0, Math.min(100, Math.abs(value) * 100));
  return (
    <div className="text-[11px]">
      <div className="flex justify-between text-slate-500">
        <span>{label}</span>
        <span className="font-mono">
          {value >= 0 ? "+" : "−"}
          {Math.abs(value).toFixed(2)}
        </span>
      </div>
      <div className="mt-0.5 h-1 overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full ${value >= 0 ? "bg-sky-400" : "bg-rose-300"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function Section({ title, total, mb }: { title: string; total: number; mb: MB | null }) {
  if (!mb || Object.keys(mb.components).length === 0) return null;
  return (
    <div>
      <div className="mb-1 text-xs font-semibold text-slate-600">
        {title} = {total.toFixed(2)}
      </div>
      <div className="space-y-1.5">
        {Object.entries(mb.components).map(([name, val]) => (
          <Bar key={name} label={name} value={val} />
        ))}
      </div>
    </div>
  );
}

export function MetricBreakdown({ h }: { h: Hypothesis }) {
  const contrib = Object.entries(h.rank_contributions ?? {}).sort(
    (a, b) => Math.abs(b[1]) - Math.abs(a[1]),
  );
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <Section title="Новизна" total={h.novelty} mb={h.novelty_breakdown} />
      <Section title="Риск" total={h.risk} mb={h.risk_breakdown} />
      <Section title="Ценность" total={h.value} mb={h.value_breakdown} />
      {contrib.length > 0 && (
        <div className="sm:col-span-3">
          <div className="mb-1 text-xs font-semibold text-slate-600">Вклад признаков в ранг</div>
          <div className="flex flex-wrap gap-1.5">
            {contrib.map(([name, val]) => (
              <span
                key={name}
                className={`pill ${
                  val >= 0 ? "bg-sky-50 text-sky-700" : "bg-rose-50 text-rose-600"
                }`}
              >
                <span className="font-mono">{name}</span>
                <span className="font-mono">
                  {val >= 0 ? "+" : "−"}
                  {Math.abs(val).toFixed(2)}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
