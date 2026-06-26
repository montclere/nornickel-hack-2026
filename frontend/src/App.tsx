// Каркас: сайдбар + вкладки (Гипотезы / Граф / Чат / Агент). Вкладка «Гипотезы» —
// мастер-деталь: слева список карточек, справа подробная панель с цепочкой-графом.

import { useState } from "react";

import { AgentTrace } from "./components/AgentTrace";
import { ChatPanel } from "./components/ChatPanel";
import { DetailPanel } from "./components/DetailPanel";
import { FullGraph } from "./components/FullGraph";
import { HypothesisCard } from "./components/HypothesisCard";
import { Sidebar } from "./components/Sidebar";
import { usePhoenix } from "./store";

type Tab = "hypotheses" | "graph" | "chat" | "agent";

const TABS: { key: Tab; label: string }[] = [
  { key: "hypotheses", label: "Гипотезы" },
  { key: "graph", label: "Граф" },
  { key: "chat", label: "Чат" },
  { key: "agent", label: "Агент" },
];

function HypothesesView() {
  const { hypotheses, selectedId, selected, generating, genError, actions } = usePhoenix();

  if (genError) {
    return (
      <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-600">
        {genError}
      </div>
    );
  }
  if (generating && hypotheses.length === 0) {
    return <div className="grid h-full place-items-center text-slate-400">Генерация гипотез…</div>;
  }
  if (hypotheses.length === 0) {
    return (
      <div className="grid h-full place-items-center text-center text-slate-400">
        <div>
          <div className="mx-auto mb-3 h-10 w-10 rounded-xl bg-gradient-to-br from-clay-200 to-clay-400" />
          Введите KPI слева и нажмите «Сгенерировать гипотезы».
        </div>
      </div>
    );
  }

  return (
    <div className="grid h-full grid-cols-1 gap-5 lg:grid-cols-[minmax(320px,420px)_1fr]">
      <div className="space-y-3 overflow-y-auto pr-1">
        <div className="text-xs text-slate-400">{hypotheses.length} гипотез · ранжировано</div>
        {hypotheses.map((h) => (
          <HypothesisCard
            key={h.id}
            h={h}
            active={h.id === selectedId}
            onClick={() => actions.select(h.id)}
          />
        ))}
      </div>
      <div className="overflow-y-auto rounded-xl border border-line bg-surface p-5">
        {selected ? (
          <DetailPanel h={selected} />
        ) : (
          <div className="grid h-full place-items-center text-slate-400">Выберите гипотезу слева.</div>
        )}
      </div>
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState<Tab>("hypotheses");

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex flex-1 flex-col overflow-hidden">
        <header className="flex items-center gap-1 border-b border-line bg-surface px-5">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`relative px-4 py-3.5 text-sm font-medium transition-colors ${
                tab === t.key ? "text-clay-600" : "text-slate-400 hover:text-slate-600"
              }`}
            >
              {t.label}
              {tab === t.key && (
                <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-clay-400" />
              )}
            </button>
          ))}
        </header>
        <section className="flex-1 overflow-hidden p-5">
          {tab === "hypotheses" && <HypothesesView />}
          {tab === "graph" && <FullGraph />}
          {tab === "chat" && <ChatPanel />}
          {tab === "agent" && <AgentTrace />}
        </section>
      </main>
    </div>
  );
}
