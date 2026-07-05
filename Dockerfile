FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-dejavu-core && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml README.md ./
COPY uv.lock* ./
COPY factory ./factory
COPY webapp ./webapp
RUN uv sync --extra web

ENV WEBAPP_RUNS_DIR=/app/outputs/runs \
    FACTORY_OUTPUTS=/app/outputs
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "webapp.main:app", "--host", "0.0.0.0", "--port", "8000"]
