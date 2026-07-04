# Локальный веб-сервис «Фабрики гипотез». НЕ для публичного развёртывания.
FROM python:3.11-slim

# шрифт с кириллицей — для PDF-экспорта (reportlab); остальное pymupdf/pillow тянут в wheel
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-dejavu-core && rm -rf /var/lib/apt/lists/*

# uv (пакетный менеджер)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
# сначала манифесты — кэш слоёв
COPY pyproject.toml README.md ./
COPY uv.lock* ./
COPY factory ./factory
COPY webapp ./webapp
RUN uv sync --extra web

ENV WEBAPP_RUNS_DIR=/app/outputs/runs \
    FACTORY_OUTPUTS=/app/outputs
EXPOSE 8000
# host 0.0.0.0 внутри контейнера; наружу пробрасываем ТОЛЬКО на localhost (см. compose)
CMD ["uv", "run", "uvicorn", "webapp.main:app", "--host", "0.0.0.0", "--port", "8000"]
