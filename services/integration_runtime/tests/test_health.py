import httpx

from integration_runtime.bootstrap.app import create_app


async def test_health_endpoints() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        assert (await c.get("/health/live")).json() == {"status": "ok"}
        assert (await c.get("/health/ready")).status_code == 200
