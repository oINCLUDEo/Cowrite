"""Адаптер шаблонов FastAPI для instrumentator без UUID в метках."""

import re
from typing import cast

from prometheus_client import Counter, Gauge
from prometheus_fastapi_instrumentator.middleware import PrometheusInstrumentatorMiddleware
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.types import ASGIApp

ws_connections = Gauge("ws_connections_active", "Active CRDT connections")
save_errors = Counter("document_save_errors", "Failed document commits")


class MetricsMiddleware(PrometheusInstrumentatorMiddleware):
    def __init__(self, app: ASGIApp, excluded_handlers: list[str]) -> None:
        super().__init__(cast(Starlette, app), excluded_handlers=excluded_handlers)

    def _get_handler(self, request: Request) -> tuple[str, bool]:
        # Новые FastAPI IncludedRouter не имеют .path. OpenAPI содержит готовые шаблоны.
        path = request.scope["path"]
        root = request.scope.get("root_path", "")
        if root and path.startswith(root):
            path = path[len(root) :]
        for template in request.app.openapi()["paths"]:
            pattern = re.sub(r"\{[^}]+\}", "[^/]+", template)
            if re.fullmatch(pattern, path):
                return str(template), True
        return "none", False
