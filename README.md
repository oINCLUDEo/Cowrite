# Cowrite

Мини-аналог Google Docs: несколько человек одновременно редактируют один документ, есть роли, история версий и экспорт в PDF.

## Текущее состояние

Реализованы регистрация и вход, список документов, роли owner/editor/viewer,
защищённое совместное редактирование с курсорами, автосохранение в PostgreSQL,
история и откат со сменой поколения, приглашения по SMTP и фоновый PDF.
Интерфейс на русском: без входа открывается форма, после входа — документы.
JWT хранится только в памяти; после перезагрузки требуется вход, адрес документа сохраняется.

Стек: Python 3.13, FastAPI, PostgreSQL 17, Redis 7.4, Celery, React 19,
TipTap 3, Yjs/pycrdt, ReportLab, Nginx, Docker Compose и GitHub Actions.
Для входа при запуске вне Compose задайте `JWT_SECRET` в `.env`: минимум
32 случайных байта. Без ключа выпуск токенов возвращает 503. Демонстрационный
ключ в Compose и `.env.example` нельзя использовать в production.

Добавлены GitHub OAuth и одноразовый обмен кода на JWT. Автоматические проверки
используют подмену GitHub; вход с настоящей OAuth App пока не проверен.
CI, публикация GHCR и SSH-деплой описаны и реализованы в workflow, но пока не
выполнялись на GitHub/VPS. Публичного HTTPS-стенда нет.

Локально пройдены 147 backend-тестов, 11 браузерных сценариев и отдельный
контейнерный acceptance.

![Редактор Cowrite](docs/editor.png)

## Локальный запуск

Нужен Docker с Docker Compose v2+. Скопируйте `.env.example` в `.env`
(PowerShell: `Copy-Item .env.example .env`), затем выполните:

```bash
docker compose up --build
```

- Приложение: <http://localhost:8080>. Зарегистрируйте двух пользователей,
  создайте документ и добавьте второго по email через «Доступ».
- Проверка API: <http://localhost:8080/api/health> → `{"status":"ok"}`.
- Swagger UI: <http://localhost:8080/api/docs>.
- Прямой API для разработки: <http://localhost:8000/health>.
- Письма Mailpit: <http://localhost:8025>.
- Prometheus: <http://localhost:9090> (метрики API извне через Nginx закрыты).
- PostgreSQL и Redis доступны только через loopback на портах 5432 и 6379.

Nginx на порту 8080 обслуживает frontend и проксирует REST/WebSocket. Сервис `migrate` применяет
миграции Alembic до запуска API. Таблицы не создаются через ORM при старте.
`/health/live` проверяет процесс; `/health/ready` — PostgreSQL и Redis.

Остановка: `docker compose down`. Именованные тома с данными сохраняются.
Данные входа в `.env.example` предназначены только для локальной разработки.
Если порты заняты, измените `API_PORT`, `POSTGRES_PORT` и `REDIS_PORT` в `.env`.
Для прямого запуска API на хосте также обновите порты в `DATABASE_URL` и
`REDIS_CACHE_URL`; внутри Compose используются стандартные контейнерные порты.

## Разработка бэкенда

Нужны Python 3.13 и [uv](https://docs.astral.sh/uv/).

```bash
cd backend
uv sync --frozen
uv run pytest --cov --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run uvicorn app.main:app --reload
```

Unit-тесты выполняются без PostgreSQL. Полный прогон требует отдельную БД
с именем, заканчивающимся на `_test`, и `TEST_DATABASE_URL`; пример создания:

```bash
docker compose exec postgres createdb -U cowrite cowrite_test
```

Задайте `TEST_DATABASE_URL=postgresql+asyncpg://cowrite:cowrite-local@127.0.0.1:5432/cowrite_test`
и `REDIS_CACHE_URL=redis://127.0.0.1:6379/0` для запуска с хоста.
Без `TEST_DATABASE_URL` PostgreSQL-тесты пропускаются — это не полный прогон.
Настройки читаются из
корневого `.env` и переменных окружения; переменные окружения имеют приоритет.
При прямом запуске API используются localhost-адреса из `.env`. В контейнере
Compose подставляет имена сервисов `postgres` и `redis`.

Интеграционные проверки и настройка защиты веток: [docs/development.md](docs/development.md).

## Проверка frontend

Нужен Node.js 22 LTS. Из каталога `frontend`:

```bash
npm ci
npm run lint
npm run build
npx playwright install chromium
npm run test:e2e
# Отдельно: перезапускает api/worker в выбранном Compose-проекте.
npm run test:acceptance
```

Браузерный тест требует запущенный Compose на порту 8080. Для другого порта
установите `E2E_BASE_URL`. Он открывает два отдельных браузерных контекста и
проверяет обмен текстом, форматирование, курсоры, откат, смену роли и reconnect.
Acceptance проверяет Mailpit, очередь при остановленном worker, повторную доставку
экспорта и сохранность текста после перезапуска API. Он запускается последовательно,
только на отдельном тестовом стенде. Для нестандартного проекта задайте
`COMPOSE_PROJECT_NAME` и те же переменные портов, что при его запуске.
При `429` тесты соблюдают `Retry-After`, защита приложения не отключается.

## GitHub OAuth

В GitHub Settings → Developer settings → OAuth Apps создайте приложение.
Callback URL должен точно совпадать с `GITHUB_REDIRECT_URI`.
Добавьте в локальный `.env`:

```dotenv
GITHUB_CLIENT_ID=идентификатор-приложения
GITHUB_CLIENT_SECRET=секрет-приложения
GITHUB_REDIRECT_URI=http://localhost:8080/api/auth/github/callback
FRONTEND_URL=http://localhost:8080
```

`JWT_SECRET` должен быть собственным случайным ключом. Перезапустите Compose
и откройте `/api/auth/github/login` в браузере. После подтверждения GitHub
callback передаст одноразовый код фронтенду; `/api/auth/exchange` обменяет его
на JWT. Cookie HttpOnly связывает обе части входа с тем же браузером.

Для тестового стенда на порту 18080 используйте этот порт в обоих URL.
После успешного OAuth открывается список документов. JWT хранится в памяти;
REST и WebSocket проверяют его и права на документ. Если GitHub-ключи не заданы,
маршрут входа возвращает 503; локальная регистрация продолжает работать.

## Документация и поставка

- [Архитектура](docs/architecture.md), [модель данных](docs/data-model.md).
- [WebSocket](docs/websocket.md), [OpenAPI](docs/openapi.json).
- Обновить REST-контракт: `cd backend` → `uv run python -m app.contracts`.
- [VPS, TLS, GHCR, выкладка и откат](docs/deployment.md).

Перед production-запуском нужно настроить OAuth App, SMTP, секреты GitHub Actions,
целевой сервер и HTTPS. Инструкции приведены в руководстве по развёртыванию.
