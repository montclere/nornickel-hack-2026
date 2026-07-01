// Панель эксперта: принять / править / отклонить с причиной → /feedback.
// После решения веса ранкера в сайдбаре сдвигаются (store обновляет weights).

import { useState } from "react";

import { usePhoenix } from "../store";
import type { Decision } from "../types";

const DECISIONS: { key: Decision; label: string; cls: string }[] = [
  { key: "accept", label: "Принять", cls: "bg-emerald-50 text-emerald-700 hover:bg-emerald-100" },
  { key: "edit", label: "Править", cls: "bg-sky-50 text-sky-700 hover:bg-sky-100" },
  { key: "reject", label: "Отклонить", cls: "bg-rose-50 text-rose-600 hover:bg-rose-100" },
];

export function FeedbackPanel({ hypothesisId }: { hypothesisId: string }) {
  const { actions } = usePhoenix();
  const [reason, setReason] = useState("");
  const [done, setDone] = useState<Decision | null>(null);

  async function decide(decision: Decision) {
    await actions.submitFeedback(hypothesisId, decision, reason || `${decision} экспертом`);
    setDone(decision);
    setTimeout(() => setDone(null), 2200);
  }

  return (
    <div>
      <div className="mb-2 text-xs font-semibold text-slate-600">Решение эксперта</div>
      <input
        className="input mb-2"
        placeholder="причина (необязательно)"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      <div className="flex gap-2">
        {DECISIONS.map((d) => (
          <button key={d.key} className={`btn flex-1 ${d.cls}`} onClick={() => decide(d.key)}>
            {d.label}
          </button>
        ))}
      </div>
      {done && (
        <div className="mt-2 animate-fade-in text-xs text-emerald-600">
          Учтено ({done}). Веса ранкера обновлены — смотрите слева.
        </div>
      )}
    </div>
  );
}
