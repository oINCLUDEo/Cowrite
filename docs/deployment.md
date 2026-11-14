# Развёртывание

**Фактический production-деплой пока не выполнен.** Нужны VPS, DNS, SSH,
GitHub-репозиторий с доступом к Packages, OAuth App и SMTP. Workflow не
является доказательством успешной публикации или доступности стенда.

## Подготовка сервера (пример для Ubuntu)

Ubuntu, GHCR и SSH — выбранный готовый вариант, не ограничение учебного задания.
Фиксированных требований к CPU/RAM и отдельного нагрузочного стенда нет.

1. Установить Docker Engine и Compose v2 с поддержкой inline configs,
   Nginx и Certbot. Открыть только 22, 80, 443. Docker-доступ равносилен root:
   выделить отдельного доверенного deploy-пользователя.
2. Настроить A/AAAA домена, получить сертификат Let's Encrypt через
   webroot `/var/www/letsencrypt`, включить автоматическое продление.
3. Установить `infra/nginx-production.conf` в Nginx, заменить домен,
   проверить `nginx -t`. Внешний HTTPS-прокси идёт на loopback:8080,
   перезаписывает X-Forwarded-For реальным IP и X-Forwarded-Proto значением https.
   Compose подключает `infra/nginx-frontend-production.conf`: внутренний прокси
   сохраняет эти значения. Не публиковать его порт на внешнем интерфейсе.
4. Создать `/opt/cowrite/.env.production`, права 600. Не коммитить файл.

Обязательные значения окружения:

```dotenv
BACKEND_IMAGE=ghcr.io/OWNER/REPOSITORY-backend
FRONTEND_IMAGE=ghcr.io/OWNER/REPOSITORY-frontend
IMAGE_TAG=40_HEX_COMMIT_SHA
POSTGRES_USER=cowrite
POSTGRES_DB=cowrite
POSTGRES_PASSWORD=REPLACE_WITH_RANDOM_PASSWORD
DATABASE_URL=postgresql+asyncpg://cowrite:URL_ENCODED_PASSWORD@postgres:5432/cowrite
REDIS_CACHE_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
JWT_SECRET=REPLACE_WITH_AT_LEAST_32_RANDOM_BYTES
API_ROOT_PATH=/api
FRONTEND_URL=https://cowrite.example.org
ALLOWED_ORIGINS=["https://cowrite.example.org"]
GITHUB_CLIENT_ID=REPLACE
GITHUB_CLIENT_SECRET=REPLACE
GITHUB_REDIRECT_URI=https://cowrite.example.org/api/auth/github/callback
SMTP_HOST=smtp.example.org
SMTP_PORT=587
SMTP_STARTTLS=true
SMTP_USERNAME=REPLACE
SMTP_PASSWORD=REPLACE
SMTP_FROM=Cowrite <noreply@example.org>
EXPORTS_DIR=/app/exports
PDF_FONTS_DIR=/usr/share/fonts/truetype/dejavu
LOG_LEVEL=INFO
```

Имена GHCR должны быть lowercase. Для приватных образов один раз выполнить
`docker login ghcr.io` на VPS с read:packages credential. Пример содержит
заполнители, не рабочие секреты. БД и Redis не имеют опубликованных портов.

## Автоматическая поставка

CI проверяет backend, frontend, покрытие, Docker и браузерный сценарий.
После успешного CI для push в main `release.yml` публикует два образа
с SHA и latest; production environment может требовать ручного approval.
Секреты environment: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`,
`DEPLOY_KNOWN_HOSTS` (проверенный отпечаток, не слепой ssh-keyscan).

`infra/deploy.sh SHA` получает образы, запускает зависимости, делает
`pg_dump -Fc`, применяет миграции и запускает приложение. Проверяются readiness
и главная страница. Текущий SHA записывается в `.release`. PostgreSQL/Redis/PDF
сохраняются в именованных томах; `down --volumes` на сервере не применяется.

## Откат и резервные копии

При ошибке после миграций скрипт возвращает предыдущие образы из `.release`.
Схема автоматически не понижается: миграции должны быть обратно совместимы.
Ручной откат — `bash infra/deploy.sh PREVIOUS_SHA`. Перед первым успешным
релизом предыдущего тега нет; требуется ручное исправление.

Дампы хранятся в `/opt/cowrite/backups` с правами 600. Настроить независимое
ежедневное копирование за пределы VPS и политику хранения. Восстановление
сначала репетируется в отдельной БД через `pg_restore`; никогда не затирать
рабочую БД без согласованного окна обслуживания. Один VPS не отказоустойчив.

## Ограничения проверки

Скрипт и Compose требуют проверки на настоящем Ubuntu/VPS. TLS, реальный OAuth,
GHCR, rollback и GitHub branch protection пока не приняты. Внешний прокси
перезаписывает X-Forwarded-For; внутренний сохраняет его. API доверяет закрытой Docker-сети;
при добавлении внешнего балансировщика требуется отдельная настройка trusted IP.
