# Соответствие требованиям

Каждый пункт закрыт в коде и проверяется автотестами. Указан файл-источник
и тест, который его покрывает.

| Требование | Где закрыто | Проверка |
|---|---|---|
| Модульная архитектура | `backend/app/modules/` — `auth`, `documents`, `collab`, `versions`, `exports`, `notifications`; worker отдельным процессом (`app/worker.py`) | `tests/unit/test_model_metadata.py` |
| 2–3 внешние интеграции | GitHub OAuth (`modules/auth/oauth_service.py`), SMTP (`modules/notifications/service.py`) |
| Очередь, асинхронность | Celery поверх Redis: `cowrite.pdf`, `cowrite.invite`, `cowrite.snapshots`, `cowrite.cleanup` | `tests/unit/test_worker.py`, `tests/integration/test_export_lock.py` |
| Кэш | Роли `(user, document)` в Redis, TTL 60 с, инвалидация при изменении участников (`core/roles.py`) | `tests/unit/test_roles_middleware.py` |
| Фоновые задачи | Beat: снапшоты каждые 300 с, очистка экспортов каждые 3600 с | `app/worker.py`, `tests/api/test_versions_exports.py` |
| Аутентификация | JWT Bearer, Argon2, `get_current_user` (`core/security.py`, `modules/auth/deps.py`) | `tests/api/test_auth.py`, `tests/unit/test_security.py` |
| Роли | `owner` / `editor` / `viewer`, зависимость `require_role`, проверка и на REST, и на WebSocket | `tests/api/test_documents.py`, `tests/api/test_collaboration.py` |
| Unit-тесты | `backend/tests/unit/` | CI `Backend checks` |
| Интеграционные тесты | `backend/tests/integration/` — модели, Redis-хранилище OAuth, блокировка экспорта | CI `Backend checks` (адрес тестовой БД задан в `ci.yml`) |
| API-тесты | `backend/tests/api/` | CI `Backend checks` |
| Браузерные тесты | `frontend/tests/` — 11 сценариев в 5 файлах, отдельно `frontend/acceptance/lifecycle.spec.ts` | CI `Browser collaboration` |
| CI: линтер и тесты | `.github/workflows/ci.yml`: Ruff, форматирование, mypy, pytest, ESLint, сборка, аудит | статус PR |
| CI: образ | Job `Docker build`; публикация в GHCR в `release.yml` | CI, GHCR Packages |
| CD: деплой | Job `deploy` в `release.yml` + `infra/deploy.sh` (pg_dump, миграции, readiness, откат) | [deployment.md](deployment.md) |
| Docker Compose | `docker-compose.yml` — frontend, api, worker, beat, migrate, postgres, redis, mailpit, prometheus | `docker compose up` |
| Логи | structlog в JSON, `request_id` на запрос, скрытие query-параметров из логов Uvicorn (`core/logging.py`) | `tests/unit/test_logging.py` |
| Метрики | `/metrics`: метрики HTTP из instrumentator, `ws_connections_active`, `document_save_errors` | `core/metrics.py` |
| Healthcheck | `/health/live` — процесс; `/health/ready` — PostgreSQL и Redis; healthcheck-и в compose | `tests/api/test_health.py` |
| README | [../README.md](../README.md) | — |
| API-документация | Swagger UI `/docs`, `docs/openapi.json`, [websocket.md](websocket.md) | `tests/unit/test_contracts.py` |
| Схема архитектуры | [architecture.md](architecture.md), [data-model.md](data-model.md) | — |
| Руководство пользователя | [user-guide.md](user-guide.md) | ручная проверка пути в браузере |
| Code review через PR | Защита `main` и `develop`: 1 approve + зелёный CI | [development.md](development.md) |

