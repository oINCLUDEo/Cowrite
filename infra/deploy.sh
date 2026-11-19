#!/usr/bin/env bash
# Запуск на подготовленном VPS из каталога приложения; секреты уже находятся там.
set -euo pipefail
cd "$(dirname "$0")/.."
tag="${1:?Commit SHA required}"
[[ "$tag" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid commit SHA' >&2; exit 2; }
test -f .env.production
export IMAGE_TAG="$tag"
compose=(docker compose --env-file .env.production -f docker-compose.prod.yml)
mkdir -p backups
chmod 700 backups
previous="$(cat .release 2>/dev/null || true)"

"${compose[@]}" pull
"${compose[@]}" up -d --wait postgres redis
backup="backups/$(date -u +%Y%m%dT%H%M%SZ).dump"
"${compose[@]}" exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup"
chmod 600 "$backup"

rollback() {
  if [[ -n "$previous" ]]; then
    export IMAGE_TAG="$previous"
    "${compose[@]}" up -d --wait --wait-timeout 180 api worker beat frontend prometheus
    echo "Application rolled back to $previous; schema was not downgraded" >&2
  fi
}
trap rollback ERR
"${compose[@]}" run --rm migrate
"${compose[@]}" up -d --wait --wait-timeout 180 api worker beat frontend prometheus
curl --fail --silent --show-error http://127.0.0.1:8080/api/health/ready > /dev/null
curl --fail --silent --show-error http://127.0.0.1:8080/ > /dev/null
printf '%s\n' "$tag" > .release
trap - ERR
