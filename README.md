# Cowrite — backend

Сервер совместного редактора документов: FastAPI, PostgreSQL, Redis,
Celery и CRDT на pycrdt. Эта ветка содержит только серверную часть;
frontend будет добавлен отдельно.

## Возможности

- Регистрация, JWT и серверная интеграция GitHub OAuth.
- Документы, участники и роли owner/editor/viewer.
- Совместное редактирование через WebSocket и сохранение CRDT в PostgreSQL.
- История версий, восстановление, фоновый экспорт PDF и SMTP-приглашения.
- Миграции Alembic, healthcheck, метрики, логи и тесты.

## Запуск

Нужен Docker Compose v2+. Скопируйте `.env.example` в `.env` и выполните:

```bash
docker compose up --build
```

- API: <http://localhost:8000>.
- Healthcheck: <http://localhost:8000/health>.
- Swagger UI: <http://localhost:8000/docs>.
- Mailpit: <http://localhost:8025>.
- Prometheus: <http://localhost:9090>.

Миграции выполняются сервисом `migrate` до запуска API и worker.
Данные сохраняются в Docker-томах после `docker compose down`.
Демонстрационные ключи и пароли не подходят для production.
GitHub OAuth требует собственную OAuth App и клиентский callback;
до добавления frontend используйте локальную регистрацию через API.

## Проверки

Нужны Python 3.13 и uv. Из каталога `backend`:

```bash
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov --cov-report=term-missing
```

Полный прогон требует `TEST_DATABASE_URL` на отдельную PostgreSQL-базу
с именем, заканчивающимся на `_test`, и доступный Redis через `REDIS_CACHE_URL`.
Без тестовой БД PostgreSQL-тесты пропускаются. CI предоставляет оба сервиса,
проверяет backend и собирает его Docker-образ.

## Документация

- [REST-контракт](docs/openapi.json).
- [WebSocket](docs/websocket.md).
- [Модель данных](docs/data-model.md).
- [План задач](TASKS.md), [правила разработки](AGENTS.md).
