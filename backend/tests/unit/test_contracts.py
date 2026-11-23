import json

from app.contracts import CONTRACT, exported_schema


def test_openapi_export_matches_application():
    assert json.loads(CONTRACT.read_text(encoding="utf-8")) == exported_schema()
