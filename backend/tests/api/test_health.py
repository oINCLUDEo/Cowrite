import httpx

from app.core.config import Settings
from app.main import create_app


async def test_health_returns_ok_without_external_services():
    app = create_app(Settings(_env_file=None))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"] == "application/json"


def test_factory_uses_provided_settings():
    app = create_app(Settings(_env_file=None, app_name="Cowrite test", debug=True))

    assert app.title == "Cowrite test"
    assert app.debug is True


def test_health_is_documented_in_openapi():
    app = create_app(Settings(_env_file=None))

    operation = app.openapi()["paths"]["/health"]["get"]
    assert "200" in operation["responses"]
