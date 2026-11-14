# Проверки и процесс разработки

## Обязательные проверки PR

Workflow `CI` запускается для PR в `develop` и `main`, push в эти ветки и вручную.
Проверки: `Backend checks`, `Frontend checks`, `Docker build` и `Browser collaboration`. Первая устанавливает зависимости
из lock-файла, запускает Ruff, форматирование, mypy и pytest с отчётом покрытия.
Проходной процент не задаётся: обязательны работающие unit/integration/API-тесты.
Docker build проверяет Compose и собирает оба образа без публикации. Frontend
checks запускает ESLint, TypeScript, сборку и аудит npm. Browser collaboration
поднимает Compose и проверяет совместное редактирование через Playwright.

Команды из каталога `backend`:

```bash
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov --cov-report=term-missing
```

Интеграционные тесты PostgreSQL требуют `TEST_DATABASE_URL` с именем БД,
оканчивающимся на `_test`. Это отдельная база, не база приложения. Без явного
адреса эти тесты пропускаются; в CI адрес задан и тесты обязательны.

## Защита веток GitHub — действие владельца

Настройки GitHub не включаются автоматически при добавлении YAML. Для веток
`main` и `develop` в Settings → Branches нужно включить:

- Require a pull request before merging.
- Required approvals: 1; Dismiss stale approvals.
- Require status checks to pass: `Backend checks`, `Frontend checks`, `Docker build`, `Browser collaboration`.
- Require branches to be up to date before merging.
- Do not allow bypassing the above settings.
- Запрет force push и удаления ветки.

Первый PR должен подтвердить работу workflow на GitHub. Проверка блокировки:
добавить нарушение Ruff, убедиться в красном статусе, исправить его и получить
зелёный статус. Проверка уже существующего кода локально не заменяет этот шаг.

## Зависимости frontend

В package.json закреплён override `minimatch >=11.0.8` для
`@typescript-eslint/typescript-estree` из-за GHSA-g3hv-75wg-m249. Замена проверена
ESLint и сборкой. Override следует удалить после исправления upstream-зависимости
и повторного аудита, не подавляя предупреждения безопасности.
