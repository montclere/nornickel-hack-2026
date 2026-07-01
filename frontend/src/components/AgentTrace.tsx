// Трейл агента: «мысль → инструмент/запрос → источник → цитата». Видно, что добыл
// агент-разведчик (/research) или чат. trace_id берётся из последнего прогона.

import { useEffect, useState } from "react";

import { api } from "../api";
import { usePhoenix } from "../store";
import type { AgentTrace as Trace } from "../types";

export function AgentTrace() {
  const { lastTraceId, researching, health, actions } = usePhoenix();
  const [traceId, setTraceId] = useState(lastTraceId ?? "");
  const [trace, setTrace] = useState<Trace | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (lastTraceId) setTraceId(lastTraceId);
  }, [lastTraceId]);

  useEffect(() => {
    if (!traceId) {
      setTrace(null);
      return;
    }
    let alive = true;
    setError(null);
    api
      .trace(traceId)
      .then((t) => alive && setTrace(t))
      .catch((e) => {
        if (alive) {
          setTrace(null);
          setError(e instanceof Error ? e.message : String(e));
        }
      });
    return () => {
      alive = false;
    };
  }, [traceId]);

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-1 text-lg font-semibold text-slate-800">Трейл агента</div>
      <p className="mb-3 text-xs text-slate-400">
        Прозрачность: мысль → запрос → источник → цитата. Видно, что именно добыл агент.
      </p>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <button
          className="btn-ghost"
          disabled={!health || researching}
          onClick={() => actions.runResearch()}
        >
          {researching ? "Разведка…" : "Запустить агента-разведчика"}
        </button>
        <input
          className="input max-w-xs"
          placeholder="trace_id"
          value={traceId}
          onChange={(e) => setTraceId(e.target.value)}
        />
      </div>

      {error && <p className="text-sm text-rose-500">{error}</p>}
      {!traceId && (
        <p className="text-sm text-slate-400">
          Запустите разведчика или задайте вопрос в чате — появится trace_id.
        </p>
      )}

      {trace && (
        <>
          <p className="mb-3 text-xs text-slate-500">
            Миссия: <span className="font-semibold text-slate-700">{trace.mission}</span> · шагов:{" "}
            {trace.steps.length}
          </p>
          <ol className="space-y-3">
            {trace.steps.map((s, i) => (
              <li key={i} className="card animate-fade-in p-4">
                <div className="text-sm font-medium text-slate-800">
                  <span className="mr-2 font-mono text-clay-500">{i + 1}</span>
                  {s.thought}
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  <span className="text-slate-400">Инструмент:</span>{" "}
                  <span className="font-mono">{s.tool}</span> ·{" "}
                  <span className="text-slate-400">запрос:</span> <em>{s.query}</em>
                </div>
                {s.evidence_quote && <p className="quote mt-2">«{s.evidence_quote}»</p>}
                {s.source_doc_id && (
                  <div className="mt-1.5 text-xs text-slate-500">
                    Источник: <span className="src-tag">{s.source_doc_id}</span>
                  </div>
                )}
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}
