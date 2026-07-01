// Чистые помощники представления (без React).

import type { Origin, Sign, Weights } from "../types";

export const FEATURE_LABELS: Record<string, string> = {
  novelty: "Новизна",
  risk: "Риск",
  value: "Ценность",
  chain_len: "Длина цепочки",
  conflict: "Противоречие",
  cost: "Стоимость",
};

export interface OriginMeta {
  label: string;
  color: string; // насыщенный цвет (точка/обводка/граф)
  soft: string; // пастельная заливка чипа
  text: string; // цвет текста на пастельной заливке
  description: string;
}

// Пастельная цветовая кодировка происхождения гипотезы.
export const ORIGIN_META: Record<Origin, OriginMeta> = {
  gap: {
    label: "Разрыв",
    color: "#5b8def",
    soft: "#e9f0fe",
    text: "#2657c9",
    description: "Свонсоновский разрыв: связь между узлами, не соединёнными в литературе.",
  },
  reanimation: {
    label: "Реанимация",
    color: "#e0975a",
    soft: "#fbeede",
    text: "#a45f1e",
    description: "Провальное направление, переоткрытое новым фактом или условием.",
  },
  contradiction: {
    label: "Противоречие",
    color: "#d96a6a",
    soft: "#fbe6e6",
    text: "#b03b3b",
    description: "Конфликт знаков влияния между источниками разных лет.",
  },
};

export function originMeta(origin: Origin): OriginMeta {
  return (
    ORIGIN_META[origin] ?? {
      label: origin,
      color: "#94a3b8",
      soft: "#eef1f5",
      text: "#475569",
      description: "",
    }
  );
}

// Палитра типов узлов графа (читаемые на светлом фоне, пастельные).
export interface NodeTypeMeta {
  label: string;
  color: string;
}

export const NODE_TYPE_META: Record<string, NodeTypeMeta> = {
  KPI: { label: "KPI", color: "#dd8a6c" },
  failure: { label: "Провал", color: "#d96a6a" },
  material: { label: "Материал", color: "#7c83e0" },
  reagent: { label: "Реагент", color: "#4fb08c" },
  parameter: { label: "Параметр", color: "#5b9bd6" },
  process: { label: "Процесс", color: "#b083d6" },
};

export function nodeTypeMeta(type: string): NodeTypeMeta {
  return NODE_TYPE_META[type] ?? { label: type, color: "#94a3b8" };
}

const SIGN_SYMBOL: Record<string, string> = { "+": "↑", "-": "↓", "0": "·" };

export function signSymbol(sign: Sign): string {
  return SIGN_SYMBOL[sign] ?? sign;
}

export function formatRub(amount: number): string {
  // ru-RU группирует разряды узким неразрывным пробелом — нормализуем к обычному
  return Math.round(amount).toLocaleString("ru-RU").replace(/[\u00A0\u202F]/g, " ") + " ₽";
}

export function formatMonths(months: number): string {
  const n = Math.round(months);
  const tail = n % 10;
  const teen = n % 100 >= 11 && n % 100 <= 14;
  let word: string;
  if (tail === 1 && !teen) word = "месяц";
  else if (tail >= 2 && tail <= 4 && !teen) word = "месяца";
  else word = "месяцев";
  return `${n} ${word}`;
}

export interface WeightRow {
  key: string;
  label: string;
  value: number;
}

export function weightRows(weights: Weights): WeightRow[] {
  const rows: WeightRow[] = [];
  for (const [key, label] of Object.entries(FEATURE_LABELS)) {
    if (key in weights) rows.push({ key, label, value: weights[key] });
  }
  for (const [key, value] of Object.entries(weights)) {
    if (!(key in FEATURE_LABELS)) rows.push({ key, label: key, value });
  }
  return rows;
}
