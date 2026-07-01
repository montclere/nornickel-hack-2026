// Тонкий HTTP-клиент к бэкенду «Феникс». Никакой бизнес-логики — только вызовы
// эндпойнтов и разбор ошибок (detail из FastAPI). Базовый адрес настраивается в UI.

import type {
  ChatResponse,
  FullGraph,
  GraphPath,
  Health,
  Hypothesis,
  AgentTrace,
  ResearchResponse,
  Weights,
  Decision,
} from "./types";

const ENV_API = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

let base = ENV_API.replace(/\/$/, "");

export function setApiBase(url: string): void {
  base = url.replace(/\/$/, "");
}
export function getApiBase(): string {
  return base;
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${base}${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail: string = res.statusText;
    try {
      const data = await res.json();
      detail = (data?.detail as string) ?? detail;
    } catch {
      /* тело не-JSON — оставляем statusText */
    }
    throw new Error(`HTTP ${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => req<Health>("GET", "/health"),
  generate: (kpi: string) => req<Hypothesis[]>("POST", "/generate", { kpi }),
  graph: () => req<FullGraph>("GET", "/graph"),
  graphPath: (id: string) => req<GraphPath>("GET", `/graph/path/${encodeURIComponent(id)}`),
  weights: () => req<Weights>("GET", "/ranker_weights"),
  feedback: (hypothesis_id: string, decision: Decision, reason: string) =>
    req<Weights>("POST", "/feedback", { hypothesis_id, decision, reason }),
  chat: (question: string, kpi: string | null) =>
    req<ChatResponse>("POST", "/chat", { question, kpi }),
  research: (kpi: string) => req<ResearchResponse>("POST", "/research", { kpi }),
  trace: (id: string) => req<AgentTrace>("GET", `/agent/trace/${encodeURIComponent(id)}`),
};
