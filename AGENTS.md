# Правила для ИИ-агентов

Этот файл читает каждая нейронка, которая работает с репозиторием. Задачи и порядок лежат в `TASKS.md`.

## Проект

Мини-аналог Google Docs: совместное редактирование в реальном времени (CRDT: `pycrdt` на сервере, Yjs в браузере), роли, история версий, экспорт в PDF.
Модульный монолит на FastAPI плюс Celery worker. Всё запускается через Docker Compose.

## Структура

```
backend/
  app/
    main.py              # создание FastAPI, подключение роутеров
    core/                # config.py, db.py, security.py, logging.py, redis.py
    modules/
      auth/              # router.py, service.py, schemas.py, deps.py
      documents/         # + models.py
      collab/            # WebSocket и комнаты pycrdt
      versions/
      exports/
      notifications/
    worker.py            # Celery app и задачи
  migrations/            # Alembic
  tests/
    unit/  integration/  api/
  pyproject.toml
  Dockerfile
frontend/                # Vite + React + TipTap
docs/
docker-compose.yml
.github/workflows/
```

Каждый модуль устроен одинаково: `router.py` (HTTP), `service.py` (логика), `schemas.py` (Pydantic), `models.py` (SQLAlchemy). Роутер не ходит в БД напрямую, только через service.

## Команды

```bash
docker compose up --build              # поднять всё
cd backend && uv run pytest            # тесты
cd backend && uv run ruff check . --fix && uv run ruff format .
cd backend && uv run alembic revision --autogenerate -m "..."   # новая миграция
```

## Правила

1. **Делай только свою задачу из `TASKS.md`.** Не переписывай чужие модули «заодно». Если без этого нельзя, сделай минимальную правку и напиши о ней в описании PR.
2. **Перед PR** должны проходить `ruff check`, `ruff format --check` и `pytest`.
3. **Каждая задача приходит с тестами**, которые проверяют её пункт «Готово, когда».
4. **Миграции:** уже смёрженные не редактируются, только создаётся новая.
5. **Настройки** только через `app/core/config.py` (pydantic-settings) и `.env`. Новую переменную сразу добавь в `.env.example`. Секреты не коммитятся.
6. **Async везде:** async SQLAlchemy, `httpx.AsyncClient`, `redis.asyncio`.
7. **Ошибки API:** через `HTTPException` с понятным `detail`. 401: нет токена, 403: нет прав, 404: нет объекта.
8. **Логи** через общий логгер из `app/core/logging.py`, без `print`.
9. **Новые зависимости** только через `uv add`. Не добавляй библиотеку, если задачу решает уже подключённая.
10. **Ветки:** работа идёт от `develop`, ветка задачи `task-NN-короткое-имя`, PR в `develop` (не в `main`). Коммиты на английском в формате `feat: …`, `fix: …`, `test: …`, `docs: …`.
11. В описании PR: номер задачи, что сделано, как проверить руками.
