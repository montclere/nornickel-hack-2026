# Кейс - фабрика научно-исследовательских гипотез

MVP для R&D-центра ГМК «Норильский никель». Доменный пилот — флотация
медно-никелевых руд, целевой KPI — извлечение Ni.

Вход: целевой KPI и база знаний (статьи, патенты, исторические отчёты о НИР, включая
провальные — часто сканы/PDF). 

Выход: ранжированный список карточек-гипотез
«ЕСЛИ — ТО — ПОТОМУ ЧТО» с цепочкой доказательств, оценками новизны/риска/ценности и
протоколом минимального эксперимента.

## Архитектура

Слоистая, с изолированным ядром.

```
app/
  config.py                 пути, пороги, модели, режимы сборки
  container.py              build(mode): собирает infra и инжектит в use-cases
  api/                      HTTP-граница (FastAPI)
  service/
    entities.py             доменные сущности (pydantic v2)
    interfaces.py           Protocol-порты подменяемых зависимостей
    domain/                 чистое ядро без I/O (детерминированное):
      generation/           генераторы гипотез + анти-грабли
      scoring/              метрики + интерпретируемый ранкер
      cards/                сборка карточки из паттерна
      graph_ops.py          запросы над графом + хеш снапшота
    pipeline/               use-cases: зовут infra, кормят domain
  infrastructure/           реализации портов (real + fake)
    sources/                OpenAlex + синтетические отчёты о НИР
    extraction/             извлечение триплетов через Groq (+ цитатный гейт)
    embeddings/             нормализация синонимов (словарь + опц. sbert)
    graph/                  GraphRepository на NetworkX
    agent/                  агент-разведчик на LangGraph (scout + chat)
    phrasing/               оформление карточек через Claude
    persistence/            SQLite: корпус, фидбек, веса ранкера
    fakes/                  детерминированные заглушки портов (оффлайн)
scripts/                    build_corpus → extract_facts → build_graph
frontend/                   SPA: React + Cytoscape + Pyvis + Tailwind
data/                       корпус/отчёты/сканы (генерируются скриптом, вне git)
fixtures/                   примеры JSON на каждую сущность
tests/
```

Правило зависимостей: `service/domain` ни на что внешнее не ссылается;
`pipeline → domain + interfaces`; `infrastructure` реализует `interfaces`;
`api → pipeline`; `container` собирает всё вместе.

Ключевой инвариант: внутри `app.service.domain` нет импортов из `app.infrastructure`
и `app.api`. Ядро не может дотянуться до LLM, сети или БД, поэтому один и тот же граф
всегда даёт один и тот же результат. Инвариант проверяется
[tests/test_isolation.py](tests/test_isolation.py) и контрактом import-linter в
[pyproject.toml](pyproject.toml).

## Установка

Нужен Python ≥ 3.11 (проверено на 3.12).

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"     # ядро (pydantic) + pytest / import-linter / ruff
pytest                       # зелёное на заглушках, без сети и GPU
lint-imports                 # контракт изоляции ядра
```

Тяжёлые зависимости вынесены в extras и ставятся по необходимости:

- `.[domain]` — networkx / numpy / scikit-learn (генераторы, скоринг, ранкер);
- `.[infra]` — fastapi / uvicorn / anthropic / sentence-transformers / pymupdf;
- `.[data]` — httpx / pillow (сборка корпуса и рендер сканов).

Скелет (`pip install -e .`) тянет только `pydantic`.

## Сборка приложения

`app.container.build(mode)` — единственная точка, где конкретные адаптеры
подключаются к use-cases:

```python
from app.container import build

c = build("fake")
triplets = c.build_knowledge_base.execute(documents)   # OCR сканов + извлечение фактов
snapshot = c.enrich_graph.execute(kpi)                 # агент-разведчик дозаполняет граф
cards    = c.generate_hypotheses.execute(kpi)          # ранжированные карточки-гипотезы
weights  = c.submit_feedback.execute(feedback)         # дообучение ранкера
answer   = c.chat.execute("почему реагент X отклонили в 2012?")  # read-only Q&A
```

`real` и `mix` собирают настоящие адаптеры там, где они готовы (phrasing, persistence),
и откатываются на заглушки для остального — поэтому `build("real")` запускается и без
сети. Каждый адаптер переключается отдельно через `PHOENIX_*` (например,
`PHOENIX_MODE=real PHOENIX_OCR=fake`); фактический выбор виден в
`container.adapter_modes` и в `GET /health`.

## Данные

Корпус собирается скриптом (нужна сеть для OpenAlex):

```bash
pip install -e ".[data]"
python scripts/build_corpus.py
```

В `data/` появляются: ~160 реальных статей по флотации Cu-Ni (`corpus.jsonl`),
16 синтетических отчётов о НИР с 9 провалами и явными причинами закрытия
(`reports.jsonl`), 5 отчётов дополнительно отрендерены в image-only PDF (`scans/` —
вход для OCR без текстового слоя) и манифест «заряженных пар» (`charged_pairs.json`):
провал по реальному реагенту + свежая статья, снимающая причину. В git данные не
хранятся — воспроизводятся скриптом.

Извлечение триплетов из корпуса (LLM через OpenAI-совместимый API, по умолчанию Groq):

```bash
echo 'GROQ_API_KEY=gsk_...' > .env     # ключ читается из .env (gitignored)
python scripts/extract_facts.py        # → data/triplets.jsonl + отчёт
```

Каждый триплет проходит цитатный гейт: `evidence_quote` обязана быть дословной
подстрокой фрагмента, иначе он отбраковывается (защита от галлюцинаций). Провайдер и
модель меняются через `llm_base_url`/`GROQ_MODEL` без правок кода; без ключа извлечение
мягко откатывается на оффлайн-фейк.

Сборка графа знаний из триплетов:

```bash
python scripts/build_graph.py          # → data/graph.json + data/snapshot.json
```

Сущности нормализуются в канонические узлы — сначала по словарю домена
(Ni/никель/nickel → один узел, остальные имена становятся `aliases`), затем по
косинусной близости ≥ `cosine_threshold` (опц., нужен `sentence-transformers`). Граф —
NetworkX MultiDiGraph: параллельные рёбра разных лет сохраняются (на них держатся
противоречия), провалы — отдельный тип `failure` с `closure_reason`. `snapshot_id` =
хеш отсортированных триплетов: один и тот же вход даёт один и тот же граф и снапшот.
В real-режиме API подхватывает `data/graph.json` вместо демо-фикстур.

## HTTP API

```bash
pip install -e ".[infra]"
uvicorn app.api:app --reload     # http://127.0.0.1:8000, Swagger на /docs
```

Сценарий через curl (на заглушках, без ключей и GPU):

```bash
curl -X POST :8000/ingest      -d '{}'                          # OCR сканов + извлечение
curl -X POST :8000/build_graph -d '{}'                          # граф + снапшот (кэш)
curl -X POST :8000/research    -d '{"kpi":"извлечение Ni +2%"}' # агент-разведчик + трейл
curl -X POST :8000/generate    -d '{"kpi":"извлечение Ni +2%"}' # ранжированные карточки
curl -X POST :8000/feedback    -d '{"hypothesis_id":"...","decision":"reject","reason":"…"}'
curl -X POST :8000/chat        -d '{"question":"почему коллектор X отклонили в 2012?"}'
```

Ещё `GET /graph` (полный граф) и `GET /graph/path/{id}` (цепочка гипотезы) в формате
Cytoscape, `GET /ranker_weights`, `GET /agent/trace/{id}`. Граф строится один раз и
кэшируется; корпус, фидбек и веса лежат в SQLite
([app/infrastructure/persistence/](app/infrastructure/persistence/)).

## Фронтенд

SPA в [frontend/](frontend/), общается с бэкендом только по HTTP.

```bash
uvicorn app.api:app                          # бэкенд на :8000
cd frontend && npm install && npm run dev    # фронт на :5173
```

Ввод KPI даёт ранжированные карточки «ЕСЛИ — ТО — ПОТОМУ ЧТО» с бейджем происхождения,
оценками с разложением по клику, предупреждением «анти-грабли» и протоколом. Цепочка
доказательств рисуется на Cytoscape — клик по ребру открывает дословную цитату и
первоисточник; отдельная вкладка показывает весь граф знаний. Эксперт
принимает/правит/отклоняет карточку, и веса ранкера сдвигаются на глазах. Плюс чат по
графу со ссылками и трейл агента. Адрес API — в сайдбаре или через `VITE_API_URL`;
подробности в [frontend/README.md](frontend/README.md).

## Что готово и что дальше

Готово: слой данных (OpenAlex + синтетические отчёты + сканы + заряженные пары),
извлечение триплетов из корпуса через LLM (Groq) с цитатным гейтом, сборку реального
графа знаний (нормализация синонимов + NetworkX + замороженный снапшот), автономного
агента-разведчика на LangGraph (ищет литературу под пробелы графа, добывает цитированные
факты, дозаполняет граф и перезамораживает снапшот), генераторы гипотез с анти-граблями,
скоринг и дообучаемый ранкер, сборку карточек с проверкой «никаких новых сущностей»,
HTTP API с SQLite-персистом и фронтенд. Полный сценарий (build_graph → research →
generate → feedback → chat) проходит на заглушках за секунды.

Прогон всего конвейера на реальных данных (160 статей → 50 триплетов → граф 68 узлов /
61 ребро) показал: приём данных, граф, чат и агент работают сквозь, а генераторы гипотез
пока заточены под форму демо-фикстур и на реальном (шумном) графе дают пусто. Это
ближайшее, что нужно доделать.

Дальше:

- устойчивые генераторы под реальный граф — gaps без жёсткой тройки `реагент→параметр→KPI`,
  contradictions с одногодичными расхождениями, reanimation с нечётким матчем причин;
- усилить нормализацию синонимов (богаче словарь + sbert-косинус), чтобы дубликаты узлов
  сливались и рёбра подтягивались к KPI;
- реальный OCR сканов (Unlimited-OCR) вместо заглушки;
- скрипт «переоткрытия»: обрезать корпус по году и показать, что топ-гипотеза
  подтверждается более поздней публикацией.
