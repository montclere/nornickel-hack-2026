// Левая панель: бренд, связь с API, ввод KPI, генерация и веса ранкера.

import { useState } from "react";

import { usePhoenix } from "../store";
import { RankerWeights } from "./RankerWeights";

export function Sidebar() {
  const { apiUrl, health, healthError, kpi, generating, actions } = usePhoenix();
  const [urlDraft, setUrlDraft] = useState(apiUrl);

  return (
    <aside className="flex h-full w-80 flex-none flex-col gap-5 overflow-y-auto border-r border-line bg-surface p-5">
      <div>
        <div className="flex items-center gap-2.5">
          <span className="inline-block h-6 w-6 rounded-md bg-gradient-to-br from-clay-300 to-clay-500" />
          <span className="text-xl font-bold tracking-tight text-slate-800">Феникс</span>
        </div>
        <p className="mt-1.5 text-xs leading-relaxed text-slate-500">
          Фабрика научно-исследовательских гипотез · R&D ГМК «Норникель»
        </p>
      </div>

      {/* связь с API */}
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-slate-500">Адрес API</label>
        <input
          className="input"
          value={urlDraft}
          onChange={(e) => setUrlDraft(e.target.value)}
          onBlur={() => actions.setApiUrl(urlDraft)}
          onKeyDown={(e) => e.key === "Enter" && actions.setApiUrl(urlDraft)}
          spellCheck={false}
        />
        <div className="flex items-center gap-2 text-xs">
          <span
            className={`inline-block h-2 w-2 rounded-full ${
              health ? "bg-emerald-500" : "bg-rose-400"
            }`}
          />
          {health ? (
            <span className="text-emerald-600">API на связи</span>
          ) : (
            <span className="text-rose-500">API недоступен</span>
          )}
        </div>
        {!health && (
          <p className="rounded-md bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-500">
            {healthError ?? "uvicorn app.api:app"}
          </p>
        )}
      </div>

      {/* KPI + генерация */}
      <div className="space-y-2">
        <label className="text-xs font-medium text-slate-500">KPI / целевая метрика</label>
        <textarea
          className="input resize-none"
          rows={2}
          value={kpi}
          onChange={(e) => actions.setKpi(e.target.value)}
        />
        <button
          className="btn-primary w-full"
          disabled={generating || !health}
          onClick={() => actions.generate()}
        >
          {generating ? "Генерация…" : "Сгенерировать гипотезы"}
        </button>
      </div>

      <div className="border-t border-line pt-4">
        <RankerWeights />
      </div>
    </aside>
  );
}
