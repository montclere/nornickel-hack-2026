// Состояние приложения и действия над API — один контекст на весь фронт.
// Компоненты остаются «глупыми»: читают состояние и зовут действия отсюда.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api, getApiBase, setApiBase } from "./api";
import type {
  ChatMessage,
  Decision,
  Health,
  Hypothesis,
  Weights,
} from "./types";

interface PhoenixState {
  apiUrl: string;
  health: Health | null;
  healthError: string | null;
  kpi: string;
  hypotheses: Hypothesis[];
  selectedId: string | null;
  weights: Weights | null;
  prevWeights: Weights | null;
  chat: ChatMessage[];
  lastTraceId: string | null;
  generating: boolean;
  chatting: boolean;
  researching: boolean;
  genError: string | null;
}

interface PhoenixActions {
  setApiUrl: (url: string) => void;
  setKpi: (kpi: string) => void;
  refreshHealth: () => Promise<void>;
  refreshWeights: () => Promise<void>;
  generate: () => Promise<void>;
  select: (id: string | null) => void;
  submitFeedback: (id: string, decision: Decision, reason: string) => Promise<void>;
  sendChat: (question: string) => Promise<void>;
  runResearch: () => Promise<void>;
}

type PhoenixContextValue = PhoenixState & {
  actions: PhoenixActions;
  selected: Hypothesis | null;
};

const PhoenixContext = createContext<PhoenixContextValue | null>(null);

export function PhoenixProvider({ children }: { children: ReactNode }) {
  const [apiUrl, setApiUrlState] = useState(getApiBase());
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [kpi, setKpi] = useState("извлечение Ni +2%");
  const [hypotheses, setHypotheses] = useState<Hypothesis[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [weights, setWeights] = useState<Weights | null>(null);
  const [prevWeights, setPrevWeights] = useState<Weights | null>(null);
  const [chat, setChat] = useState<ChatMessage[]>([]);
  const [lastTraceId, setLastTraceId] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [chatting, setChatting] = useState(false);
  const [researching, setResearching] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await api.health());
      setHealthError(null);
    } catch (e) {
      setHealth(null);
      setHealthError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const refreshWeights = useCallback(async () => {
    try {
      setWeights(await api.weights());
    } catch {
      /* веса появятся, когда бэкенд поднимется */
    }
  }, []);

  const setApiUrl = useCallback(
    (url: string) => {
      setApiBase(url);
      setApiUrlState(getApiBase());
      void refreshHealth();
      void refreshWeights();
    },
    [refreshHealth, refreshWeights],
  );

  const generate = useCallback(async () => {
    setGenerating(true);
    setGenError(null);
    try {
      const cards = await api.generate(kpi);
      setHypotheses(cards);
      setSelectedId(cards.length ? cards[0].id : null);
      await refreshWeights();
    } catch (e) {
      setGenError(e instanceof Error ? e.message : String(e));
      setHypotheses([]);
      setSelectedId(null);
    } finally {
      setGenerating(false);
    }
  }, [kpi, refreshWeights]);

  const select = useCallback((id: string | null) => setSelectedId(id), []);

  const submitFeedback = useCallback(
    async (id: string, decision: Decision, reason: string) => {
      setPrevWeights(weights);
      try {
        const next = await api.feedback(id, decision, reason);
        setWeights(next);
      } catch (e) {
        // показываем ошибку как системное сообщение в чате-агностике — через genError
        setGenError(e instanceof Error ? e.message : String(e));
      }
    },
    [weights],
  );

  const sendChat = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q) return;
      setChat((prev) => [...prev, { role: "user", content: q }]);
      setChatting(true);
      try {
        const res = await api.chat(q, kpi || null);
        setChat((prev) => [
          ...prev,
          { role: "assistant", content: res.answer, sources: res.sources },
        ]);
        if (res.trace_id) setLastTraceId(res.trace_id);
      } catch (e) {
        setChat((prev) => [
          ...prev,
          {
            role: "assistant",
            content: `Ошибка: ${e instanceof Error ? e.message : e}`,
            sources: [],
          },
        ]);
      } finally {
        setChatting(false);
      }
    },
    [kpi],
  );

  const runResearch = useCallback(async () => {
    setResearching(true);
    try {
      const res = await api.research(kpi);
      if (res.trace_id) setLastTraceId(res.trace_id);
    } catch (e) {
      setGenError(e instanceof Error ? e.message : String(e));
    } finally {
      setResearching(false);
    }
  }, [kpi]);

  // первичная загрузка: проверка связи + текущие веса
  useEffect(() => {
    void refreshHealth();
    void refreshWeights();
  }, [refreshHealth, refreshWeights]);

  const selected = useMemo(
    () => hypotheses.find((h) => h.id === selectedId) ?? null,
    [hypotheses, selectedId],
  );

  const value: PhoenixContextValue = {
    apiUrl,
    health,
    healthError,
    kpi,
    hypotheses,
    selectedId,
    weights,
    prevWeights,
    chat,
    lastTraceId,
    generating,
    chatting,
    researching,
    genError,
    selected,
    actions: {
      setApiUrl,
      setKpi,
      refreshHealth,
      refreshWeights,
      generate,
      select,
      submitFeedback,
      sendChat,
      runResearch,
    },
  };

  return <PhoenixContext.Provider value={value}>{children}</PhoenixContext.Provider>;
}

export function usePhoenix(): PhoenixContextValue {
  const ctx = useContext(PhoenixContext);
  if (!ctx) throw new Error("usePhoenix должен вызываться внутри <PhoenixProvider>");
  return ctx;
}
