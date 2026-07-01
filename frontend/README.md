# Феникс — фронтенд (React + Cytoscape + Tailwind)

Кликабельный интерфейс над HTTP-API бэкенда. Центр интерпретируемости — цепочка
доказательств на Cytoscape: клик по ребру раскрывает дословную цитату и первоисточник.
Фронт общается с бэкендом только по HTTP (CORS на бэке открыт), ядро не импортирует.

## Запуск

```bash
# 1) бэкенд (из корня репозитория)
uvicorn app.api:app                 # http://localhost:8000

# 2) фронтенд (отсюда)
npm install
npm run dev                         # http://localhost:5173
```

Адрес API по умолчанию — `http://localhost:8000`; меняется в сайдбаре или через
`VITE_API_URL` (см. `.env.example`).

## Что внутри

| Экран | Эндпойнт | Что делает |
|---|---|---|
| Ввод KPI → карточки | `POST /generate` | ранжированные гипотезы ЕСЛИ-ТО-ПОТОМУ ЧТО |
| Карточка | — | бейдж происхождения, метрики с разложением, анти-грабли, протокол |
| Цепочка доказательств | `GET /graph/path/{id}` | Cytoscape-граф; клик по ребру → цитата + источник |
| Панель эксперта | `POST /feedback` | принять/править/отклонить → веса ранкера сдвигаются |
| Веса ранкера | `GET /ranker_weights` | живые полосы с дельтой после фидбека |
| Чат по графу | `POST /chat` | ответы со ссылками (read-only) |
| Трейл агента | `POST /research`, `GET /agent/trace/{id}` | мысль → запрос → источник → цитата |

## Структура

```
src/
  api.ts              HTTP-клиент ко всем эндпойнтам
  types.ts            зеркало pydantic-сущностей бэкенда
  store.tsx           состояние + действия (React Context)
  lib/format.ts       чистые помощники представления
  components/         Sidebar, RankerWeights, HypothesisCard, DetailPanel,
                      EvidenceGraph (Cytoscape), MetricBreakdown, FeedbackPanel,
                      ChatPanel, AgentTrace
```

Сборка прод-бандла: `npm run build` (типизация `tsc --noEmit` + `vite build` → `dist/`).
