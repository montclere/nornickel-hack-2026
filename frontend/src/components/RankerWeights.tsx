// Веса ранкера как «живые» полосы: после фидбека значения сдвигаются на глазах,
// рядом — дельта относительно предыдущих весов.

import { usePhoenix } from "../store";
import { weightRows } from "../lib/format";

// нормировка веса [-2, 2] → ширина полосы [0, 100%]
function widthPct(value: number): number {
  return Math.max(0, Math.min(100, ((value + 2) / 4) * 100));
}

export function RankerWeights() {
  const { weights, prevWeights } = usePhoenix();

  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-700">Веса ранкера</h3>
      <p className="mb-3 mt-0.5 text-[11px] leading-snug text-slate-400">
        Интерпретируемые веса признаков. Дообучаются на решениях эксперта.
      </p>
      {!weights ? (
        <p className="text-xs text-slate-400">—</p>
      ) : (
        <div className="space-y-2.5">
          {weightRows(weights).map(({ key, label, value }) => {
            const delta = value - (prevWeights?.[key] ?? value);
            const moved = Math.abs(delta) > 1e-6;
            return (
              <div key={key}>
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-slate-500">{label}</span>
                  <span className="font-mono text-slate-600">
                    {value.toFixed(2)}
                    {moved && (
                      <span className={delta > 0 ? "text-emerald-600" : "text-rose-500"}>
                        {" "}
                        {delta > 0 ? "+" : "−"}
                        {Math.abs(delta).toFixed(2)}
                      </span>
                    )}
                  </span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      value >= 0 ? "bg-clay-400" : "bg-slate-400"
                    }`}
                    style={{ width: `${widthPct(value)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
