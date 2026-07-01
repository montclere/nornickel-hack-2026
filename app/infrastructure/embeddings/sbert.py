"""Эмбеддинги (sentence-transformers) и нормализация сущностей в узлы графа.

Склейка синонимов идёт в два шага:
  1) канонический словарь домена (CANONICAL_DICT) — точный/подстрочный матч
     (Ni/никель/nickel → "Ni", ксантогенат/xanthate → "xanthate" и т.п.);
  2) для имён вне словаря — склейка по косинусной близости ≥ порога (если задан
     эмбеддер). Без эмбеддера шаг 2 пропускается (каждое имя — свой узел).

Детерминизм: строки обрабатываются в отсортированном порядке, в кластер сливаются
в первый подходящий репрезентант — один и тот же вход даёт один и тот же результат.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.config import Settings, load_settings
from app.service.entities import Node

_WS = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Привести имя сущности к ключу сравнения: нижний регистр, схлопнутые пробелы."""
    return _WS.sub(" ", text).strip().lower()


# Канонический словарь домена: id, человекочитаемый label, тип узла и синонимы
# (в т.ч. кросс-языковые и сокращения). Это основной механизм склейки.
CANONICAL_DICT: list[dict] = [
    {"id": "Ni_recovery", "label": "Извлечение Ni", "type": "KPI",
     "synonyms": ["извлечение ni", "извлечение никеля", "nickel recovery", "ni recovery",
                  "recovery of nickel", "извлечение ni +2%"]},
    {"id": "Cu_recovery", "label": "Извлечение Cu", "type": "KPI",
     "synonyms": ["извлечение cu", "извлечение меди", "copper recovery", "cu recovery"]},
    {"id": "Ni", "label": "Никель", "type": "material",
     "synonyms": ["ni", "никель", "nickel"]},
    {"id": "Cu", "label": "Медь", "type": "material",
     "synonyms": ["cu", "медь", "copper"]},
    {"id": "pentlandite", "label": "Пентландит", "type": "material",
     "synonyms": ["пентландит", "pentlandite"]},
    {"id": "pyrrhotite", "label": "Пирротин", "type": "material",
     "synonyms": ["пирротин", "pyrrhotite"]},
    {"id": "chalcopyrite", "label": "Халькопирит", "type": "material",
     "synonyms": ["халькопирит", "chalcopyrite"]},
    {"id": "pH", "label": "pH пульпы", "type": "parameter",
     "synonyms": ["ph", "ph пульпы", "pulp ph", "рн пульпы"]},
    {"id": "Eh", "label": "Eh пульпы", "type": "parameter",
     "synonyms": ["eh", "eh пульпы", "redox potential",
                  "окислительно-восстановительный потенциал"]},
    {"id": "temperature", "label": "Температура пульпы", "type": "parameter",
     "synonyms": ["температура", "температура пульпы", "temperature", "подогрев пульпы"]},
    {"id": "xanthate", "label": "Ксантогенат", "type": "reagent",
     "synonyms": ["ксантогенат", "xanthate", "бутиловый ксантогенат", "butyl xanthate"]},
    {"id": "CMC", "label": "Карбоксиметилцеллюлоза", "type": "reagent",
     "synonyms": ["cmc", "карбоксиметилцеллюлоза", "carboxymethyl cellulose",
                  "carboxymethyl-cellulose"]},
    {"id": "SMBS", "label": "Метабисульфит натрия", "type": "reagent",
     "synonyms": ["smbs", "метабисульфит натрия", "метабисульфит", "sodium metabisulfite",
                  "sodium metabisulphite", "metabisulfite", "metabisulphite"]},
    {"id": "dextrin", "label": "Декстрин", "type": "reagent",
     "synonyms": ["декстрин", "dextrin"]},
    {"id": "lime", "label": "Известь", "type": "reagent",
     "synonyms": ["известь", "lime"]},
    {"id": "dithiophosphinate", "label": "Дитиофосфинатный собиратель", "type": "reagent",
     "synonyms": ["дитиофосфинат", "дитиофосфинатный собиратель", "dithiophosphinate",
                  "dithiophosphate", "aerophine"]},
    {"id": "collector", "label": "Собиратель", "type": "reagent",
     "synonyms": ["собиратель", "collector", "селективный собиратель", "selective collector"]},
    {"id": "depressant", "label": "Депрессор", "type": "reagent",
     "synonyms": ["депрессор", "депрессант", "depressant"]},
    {"id": "frother", "label": "Пенообразователь", "type": "reagent",
     "synonyms": ["пенообразователь", "frother", "мибк", "mibc"]},
    {"id": "flotation", "label": "Флотация", "type": "process",
     "synonyms": ["флотация", "flotation", "флотационный передел"]},
    {"id": "column_flotation", "label": "Колонная флотация", "type": "process",
     "synonyms": ["колонная флотация", "column flotation"]},
]

_TYPE_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("извлечен", "recovery", "kpi", "selectivity", "селективн"), "KPI"),
    (("ph", "eh", "температур", "temperatur", "расход", "доз", "потенциал", "давлен"), "parameter"),
    (("флотац", "flotation", "сепарац", "процесс", "process"), "process"),
    (("собиратель", "collector", "депрес", "depressant", "реагент", "reagent", "ксантоген",
      "xanthate", "пенообраз", "frother", "кислот", "acid"), "reagent"),
    (("закрыт", "провал", "failure", "отказ"), "failure"),
]


def infer_type(name: str) -> str:
    """Эвристический тип для сущности вне словаря (по ключевым словам)."""
    low = name.lower()
    for keys, node_type in _TYPE_KEYWORDS:
        if any(k in low for k in keys):
            return node_type
    return "material"


def slug(name: str) -> str:
    """Стабильный id-слаг из имени (сохраняем кириллицу, схлопываем разделители)."""
    s = re.sub(r"[^0-9a-zа-яё]+", "_", name.strip().lower())
    return s.strip("_") or "node"


@dataclass
class Normalization:
    """Результат нормализации: отображение строки → id узла и список узлов."""

    node_of: dict[str, str] = field(default_factory=dict)
    nodes: list[Node] = field(default_factory=list)


class EntityNormalizer:
    """Склейка имён сущностей в канонические узлы (словарь + опц. косинус)."""

    def __init__(
        self,
        canonical_dict: list[dict] | None = None,
        embedder: object | None = None,
        threshold: float | None = None,
        settings: Settings | None = None,
    ) -> None:
        settings = settings or load_settings()
        self.threshold = threshold if threshold is not None else settings.cosine_threshold
        self.embedder = embedder
        self._dict = canonical_dict or CANONICAL_DICT
        # точный матч: синоним/label → запись; подстрочный — для синонимов длиннее 3
        self._exact: dict[str, dict] = {}
        self._substr: list[tuple[str, dict]] = []
        for entry in self._dict:
            for syn in [entry["label"].lower(), *entry["synonyms"]]:
                key = normalize_text(syn)
                self._exact.setdefault(key, entry)
                if len(key) > 3:
                    self._substr.append((key, entry))
        # длинные синонимы раньше — берём самый длинный матч (детерминированно)
        self._substr.sort(key=lambda kv: (-len(kv[0]), kv[1]["id"]))

    # --- публичный контракт ---

    def normalize(self, names: list[str] | set[str]) -> Normalization:
        node_of: dict[str, str] = {}
        nodes: dict[str, dict] = {}  # id → {label, type, aliases:set, closure_reason}
        unknown: list[str] = []

        for name in sorted(set(names)):
            entry = self._match(normalize_text(name))
            if entry is None:
                unknown.append(name)
                continue
            cid = entry["id"]
            node_of[name] = cid
            slot = nodes.setdefault(
                cid, {"label": entry["label"], "type": entry["type"], "aliases": set()}
            )
            if normalize_text(name) != normalize_text(entry["label"]):
                slot["aliases"].add(name)

        # имена вне словаря: косинусная склейка (если есть эмбеддер) или каждое — свой узел
        for rep, members in self._cluster_unknown(unknown).items():
            cid = slug(rep)
            while cid in nodes:  # коллизия слагов — разводим
                cid += "_"
            aliases = {m for m in members if m != rep}
            nodes[cid] = {"label": rep, "type": infer_type(rep), "aliases": aliases}
            for m in members:
                node_of[m] = cid

        node_list = [
            Node(id=cid, label=d["label"], type=d["type"], aliases=sorted(d["aliases"]))
            for cid, d in sorted(nodes.items())
        ]
        return Normalization(node_of=node_of, nodes=node_list)

    # --- внутреннее ---

    def _match(self, key: str) -> dict | None:
        if key in self._exact:
            return self._exact[key]
        for syn, entry in self._substr:  # отсортированы по убыванию длины
            if syn in key:
                return entry
        return None

    def _cluster_unknown(self, unknown: list[str]) -> dict[str, list[str]]:
        ordered = sorted(set(unknown))
        if self.embedder is None or len(ordered) < 2:
            return {name: [name] for name in ordered}
        vecs = self.embedder.encode(ordered)  # нормированные векторы
        reps: list[tuple[str, int]] = []
        cluster_of: dict[str, str] = {}
        for i, name in enumerate(ordered):
            best_rep, best_sim = None, -1.0
            for rep_name, rep_idx in reps:
                sim = float((vecs[i] * vecs[rep_idx]).sum())  # косинус (векторы нормированы)
                if sim > best_sim:
                    best_sim, best_rep = sim, rep_name
            if best_rep is not None and best_sim >= self.threshold:
                cluster_of[name] = best_rep
            else:
                reps.append((name, i))
                cluster_of[name] = name
        clusters: dict[str, list[str]] = {}
        for name, rep in cluster_of.items():
            clusters.setdefault(rep, []).append(name)
        return clusters


class SbertEmbedding:
    """Мультиязычные эмбеддинги через sentence-transformers (ленивый импорт).

    Возвращает L2-нормированные векторы (скалярное произведение = косинус).
    Сид фиксируется для воспроизводимости (инференс sbert и так детерминирован).
    """

    def __init__(
        self,
        model_name: str | None = None,
        settings: Settings | None = None,
        seed: int = 42,
    ) -> None:
        self.model_name = model_name or (settings or load_settings()).embedding_model
        self.seed = seed
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover — зависит от окружения
                raise RuntimeError(
                    "SbertEmbedding требует sentence-transformers: pip install -e '.[infra]'"
                ) from exc
            import numpy as np

            np.random.seed(self.seed)
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: list[str]):
        model = self._load()
        return model.encode(list(texts), normalize_embeddings=True, convert_to_numpy=True)


__all__ = [
    "SbertEmbedding",
    "EntityNormalizer",
    "Normalization",
    "CANONICAL_DICT",
    "normalize_text",
    "infer_type",
    "slug",
]
