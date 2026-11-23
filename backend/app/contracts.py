"""Воспроизводимая выгрузка REST-контракта: uv run python -m app.contracts."""

import json
from pathlib import Path

from app.core.config import Settings
from app.main import create_app

CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"


def exported_schema() -> dict[str, object]:
    return create_app(Settings(_env_file=None)).openapi()


if __name__ == "__main__":
    CONTRACT.write_text(
        json.dumps(exported_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
