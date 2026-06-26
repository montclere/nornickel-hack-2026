// Подробная панель выбранной гипотезы: формула, цепочка-граф (центр интерпретируемости),
// разложение оценок, протокол, панель эксперта.

import type { ReactNode } from "react";

import { formatMonths, formatRub, originMeta } from "../lib/format";
import type { Hypothesis } from "../types";
import { EvidenceGraph } from "./EvidenceGraph";
import { FeedbackPanel } from "./FeedbackPanel";
import { MetricBreakdown } from "./MetricBreakdown";

function Chevron() {
  return (
    <svg
      className="h-3.5 w-3.5 transition-transform group-open:rotate-90"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="9 6 15 12 9 18" />
    </svg>
  );
}

function Disclosure({ summary, children, open = false }: { summary: string; children: ReactNode; open?: boolean }) {
  return (
    <details open={open} className="group rounded-lg border border-line bg-slate-50/60">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 px-3 py-2 text-sm font-medium text-slate-600 marker:content-none hover:text-slate-800">
        <Chevron />
        {summary}
      </summary>
      <div className="border-t border-line p-3">{children}</div>
    </details>
  );
}

export function DetailPanel({ h }: { h: Hypothesis }) {
  const meta = originMeta(h.origin);
  const proto = h.experiment_protocol;
  const gy = h.graveyard_check;

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center justify-between">
          <span className="pill" style={{ background: meta.soft, color: meta.text }}>
            {meta.label}
          </span>
          <span className="font-mono text-xs text-slate-400">{h.id}</span>
        </div>
        <p className="mt-3 text-base leading-relaxed text-slate-800">
          <span className="font-semibold text-clay-500">ЕСЛИ</span> {h.statement_if}
          <br />
          <span className="font-semibold text-clay-500">ТО</span> {h.statement_then}
          <br />
          <span className="font-semibold text-clay-500">ПОТОМУ ЧТО</span> {h.statement_because}
        </p>
        <p className="mt-2 text-xs text-slate-400">{meta.description}</p>
      </div>

      {gy?.warning && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          <span className="font-semibold">Анти-грабли:</span>{" "}
          {gy.reason ?? "перекликается с провальным направлением"}.
          {gy.difference && <> Отличие: {gy.difference}.</>}{" "}
          {gy.report_ref && <span className="src-tag">{gy.report_ref}</span>}
        </div>
      )}
      {h.phrasing_flag && (
        <div className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-800">
          Заземление: {h.phrasing_flag}
        </div>
      )}

      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-700">Цепочка доказательств</h3>
        <EvidenceGraph hypothesisId={h.id} />
      </div>

      <Disclosure summary="Разложение оценок и вклад в ранг">
        <MetricBreakdown h={h} />
      </Disclosure>

      <Disclosure summary="Протокол минимального эксперимента">
        <div className="grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
          <div><span className="text-slate-400">Метод:</span> {proto.method}</div>
          <div><span className="text-slate-400">Оборудование:</span> {proto.equipment}</div>
          <div>
            <span className="text-slate-400">Срок:</span>{" "}
            {formatMonths(Math.max(1, Math.round(proto.duration_days / 30)))}{" "}
            <span className="text-slate-400">({proto.duration_days} дн.)</span>
          </div>
          <div><span className="text-slate-400">Стоимость:</span> {formatRub(proto.cost_rub)}</div>
        </div>
        {h.sources.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs">
            <span className="text-slate-400">Источники:</span>
            {h.sources.map((s) => (
              <span key={s} className="src-tag">{s}</span>
            ))}
          </div>
        )}
      </Disclosure>

      <div className="card p-4">
        <FeedbackPanel hypothesisId={h.id} />
      </div>
    </div>
  );
}
