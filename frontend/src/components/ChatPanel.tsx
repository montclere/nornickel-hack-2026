// Чат по графу (read-only): вопрос → /chat, ответ со ссылками на первоисточники.

import { useEffect, useRef, useState } from "react";

import { usePhoenix } from "../store";

export function ChatPanel() {
  const { chat, chatting, health, actions } = usePhoenix();
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat, chatting]);

  function submit() {
    const q = draft.trim();
    if (!q) return;
    setDraft("");
    void actions.sendChat(q);
  }

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col">
      <div className="mb-1 text-lg font-semibold text-slate-800">Чат по графу знаний</div>
      <p className="mb-3 text-xs text-slate-400">
        Ответы строятся по первоисточникам. Граф при этом не меняется (read-only).
      </p>

      <div className="flex-1 space-y-3 overflow-y-auto rounded-lg border border-line bg-surface p-4">
        {chat.length === 0 && (
          <p className="text-sm text-slate-400">
            Спросите про граф: связи, провалы, противоречия. Напр.: «почему коллектор X
            отклонили в 2012?»
          </p>
        )}
        {chat.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${
                m.role === "user"
                  ? "bg-clay-400 text-white"
                  : "border border-line bg-slate-50 text-slate-700"
              }`}
            >
              <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>
              {m.sources && m.sources.length > 0 && (
                <div
                  className={`mt-2 flex flex-wrap gap-1.5 border-t pt-2 ${
                    m.role === "user" ? "border-white/30" : "border-line"
                  }`}
                >
                  {m.sources.map((s) => (
                    <span
                      key={s}
                      className={`font-mono text-xs ${
                        m.role === "user" ? "text-white/90" : "text-sky-600"
                      }`}
                    >
                      {s}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {chatting && <div className="text-xs text-slate-400">Феникс думает…</div>}
        <div ref={endRef} />
      </div>

      <div className="mt-3 flex gap-2">
        <input
          className="input"
          placeholder="ваш вопрос к графу…"
          value={draft}
          disabled={!health}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        <button className="btn-primary" disabled={!health || chatting} onClick={submit}>
          Спросить
        </button>
      </div>
    </div>
  );
}
