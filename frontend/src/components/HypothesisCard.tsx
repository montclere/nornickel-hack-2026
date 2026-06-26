// Компактная карточка в списке: бейдж происхождения, формула, метрики, анти-грабли.
// Клик → выбор для подробной панели справа.

import { originMeta } from "../lib/format";
import type { Hypothesis } from "../types";

function Metric({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="flex flex-col items-center">
      <span className={`font-mono text-sm font-semibold ${tone}`}>{value.toFixed(2)}</span>
      <span className="text-[10px] uppercase tracking-wide text-slate-400">{label}</span>
    </div>
  );
}

export function HypothesisCard({
  h,
  active,
  onClick,
}: {
  h: Hypothesis;
  active: boolean;
  onClick: () => void;
}) {
  const meta = originMeta(h.origin);
  return (
    <button
      onClick={onClick}
      className={`card animate-fade-in w-full p-4 text-left ${
        active ? "ring-2 ring-clay-300" : "hover:border-slate-300"
      }`}
      style={{ borderLeft: `3px solid ${meta.color}` }}
    >
      <div className="flex items-center justify-between">
        <span className="pill" style={{ background: meta.soft, color: meta.text }}>
          {meta.label}
        </span>
        <div className="flex items-center gap-2">
          {h.graveyard_check?.warning && (
            <span
              className="pill bg-amber-50 text-amber-700"
              title={h.graveyard_check.reason ?? ""}
            >
              анти-грабли
            </span>
          )}
          {h.rank_score != null && (
            <span className="text-xs text-slate-400">
              ранг <span className="font-mono text-clay-500">{h.rank_score.toFixed(2)}</span>
            </span>
          )}
        </div>
      </div>

      <p className="mt-2 text-sm leading-snug text-slate-700">
        <span className="font-semibold text-clay-500">ЕСЛИ</span> {h.statement_if}{" "}
        <span className="font-semibold text-clay-500">ТО</span> {h.statement_then}
      </p>

      <div className="mt-3 flex justify-around border-t border-line pt-2">
        <Metric label="новизна" value={h.novelty} tone="text-sky-600" />
        <Metric label="риск" value={h.risk} tone="text-rose-500" />
        <Metric label="ценность" value={h.value} tone="text-emerald-600" />
      </div>
    </button>
  );
}
