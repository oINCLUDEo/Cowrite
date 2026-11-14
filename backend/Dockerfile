FROM ghcr.io/astral-sh/uv:0.13.8 AS uv

FROM python:3.13-slim

COPY --from=uv /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core fonts-dejavu-extra && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
# Зависимости кэшируются отдельно от кода; тестовые инструменты в образ не входят.
RUN uv sync --frozen --no-dev

RUN groupadd --system cowrite && useradd --system --gid cowrite --no-create-home cowrite
RUN mkdir -p /app/exports && chown cowrite:cowrite /app/exports
COPY --chown=cowrite:cowrite app ./app
COPY --chown=cowrite:cowrite alembic.ini ./
COPY --chown=cowrite:cowrite migrations ./migrations

USER cowrite
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).close()"]

# Один процесс: CRDT-комнаты пока хранятся в его памяти без межпроцессной синхронизации.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
