"""Fon ishlari: osilgan vazifa, retention, tozalash qayta urinishi, eski draftlar, tenant ro‘yxati."""

from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from business.entrypoints.jobs import MaintenanceStats, run_for_tenant, tenant_ids
from business.platform.db import tenant_transaction
from business.platform.storage import ObjectRef
from tests.unit.documents.samples import make_docx

from .test_documents import owner, process, upload
from .test_identity_http import csrf

pytestmark = pytest.mark.integration


async def sql(engine: AsyncEngine, tenant: UUID, query: str, **params: object) -> list[object]:
    async with tenant_transaction(engine, tenant_id=tenant, user_id=None) as conn:
        result = await conn.execute(text(query), params)
        return list(result.all()) if result.returns_rows else []


async def maintain(client: httpx.AsyncClient, tenant: UUID) -> MaintenanceStats:
    container = client._transport.app.state.container  # type: ignore[attr-defined]
    stats = MaintenanceStats()
    await run_for_tenant(container, tenant, stats)
    return stats


async def test_reaper_fails_stuck_task_releases_budget_and_pumps_queue(
        client: httpx.AsyncClient, app_engine: AsyncEngine) -> None:
    container = client._transport.app.state.container  # type: ignore[attr-defined]
    container.settings.agent_parallel_limit = 1
    try:
        async with owner(client, "Osilgan MChJ") as (c, tenant):
            assert tenant in await tenant_ids(container)  # trigger: yangi tenant ro‘yxatda
            conv = (await c.post("/api/v1/conversations", headers=csrf(c), json={})).json()["id"]
            url = f"/api/v1/conversations/{conv}/messages"
            stuck = (await c.post(url, headers=csrf(c), json={"content": "Ali, savdo"})).json()
            waiting = (await c.post(url, headers=csrf(c), json={"content": "Ali, savdo 2"})).json()
            assert waiting["queue_position"] == 1
            await sql(app_engine, tenant, "UPDATE workspace.tasks SET dispatched_at ="
                      " now() - interval '20 minutes' WHERE id = :id", id=stuck["task_id"])

            stats = await maintain(client, tenant)
            assert stats.reaped == 1
            task = (await c.get(f"/api/v1/tasks/{stuck['task_id']}")).json()
            assert (task["status"], task["error_code"]) == ("failed", "TASK_TIMEOUT")
            assert (await c.get(f"/api/v1/tasks/{waiting['task_id']}")).json()[
                "queue_position"] is None  # slot bo‘shadi — keyingisi yuborildi
            rows = await sql(app_engine, tenant, "SELECT status FROM governance.budget_usage"
                             " WHERE task_id = :id", id=stuck["task_id"])
            assert rows[0][0] == "released"  # type: ignore[index]
            assert any("belgilangan vaqt ichida" in m["content"]
                       for m in (await c.get(url)).json())
            assert (await maintain(client, tenant)).reaped == 0  # takroriy ishga tushirish xavfsiz
    finally:
        container.settings.agent_parallel_limit = 3


async def test_retention_and_document_jobs(client: httpx.AsyncClient, app_engine: AsyncEngine,
                                           tmp_path: Path) -> None:
    async with owner(client, "Retention MChJ") as (c, tenant):
        old = (await c.post("/api/v1/conversations", headers=csrf(c), json={})).json()["id"]
        fresh = (await c.post("/api/v1/conversations", headers=csrf(c), json={})).json()["id"]
        await sql(app_engine, tenant, "UPDATE workspace.conversations SET updated_at ="
                  " now() - interval '100 days' WHERE id = :id", id=old)

        doc = await upload(c, make_docx(tmp_path / "Eski.docx"))
        await process(client, app_engine, tenant, doc)
        draft = (await c.post(f"/api/v1/documents/{doc['id']}/drafts", headers=csrf(c), json={
            "base_version_id": doc["version_id"], "expected_version_id": doc["version_id"],
            "operations": [{"section_id": "p2", "find": "15 kun", "replace": "30 kun"}]})).json()
        await sql(app_engine, tenant, "UPDATE documents.versions SET created_at ="
                  " now() - interval '100 days' WHERE id = :id", id=draft["draft_version_id"])
        (key,) = (await sql(app_engine, tenant, "SELECT bucket, object_key FROM documents.versions"
                            " WHERE id = :id", id=draft["draft_version_id"]))
        job = uuid4()
        await sql(app_engine, tenant, "INSERT INTO documents.cleanup_jobs (tenant_id, id,"
                  " document_id, status, attempts, last_error, created_at) VALUES (:t, :id, :d,"
                  " 'failed', 1, 'S3 timeout', now() - interval '30 minutes')",
                  t=tenant, id=job, d=doc["id"])

        stats = await maintain(client, tenant)
        assert (stats.conversations_purged, stats.drafts_purged, stats.cleanups_retried) == (1, 1, 1)
        ids = {x["id"] for x in (await c.get("/api/v1/conversations")).json()}
        assert old not in ids and fresh in ids
        detail = (await c.get(f"/api/v1/documents/{doc['id']}")).json()
        assert [v["id"] for v in detail["versions"]] == [doc["version_id"]]  # asl nusxa qoladi
        container = client._transport.app.state.container  # type: ignore[attr-defined]
        with pytest.raises(Exception):  # noqa: B017 — draft fayli ombordan o‘chgan
            await container.storage.download_to(ObjectRef(key[0], key[1], "0" * 64, 0),  # type: ignore[index]
                                                tmp_path / "x")
        published = await sql(app_engine, tenant, "SELECT count(*) FROM messaging.outbox WHERE"
                              " event_type = 'CleanupDocument.v1' AND"
                              " envelope->'payload'->>'cleanup_job_id' = :j", j=str(job))
        assert published[0][0] == 1  # type: ignore[index]


async def test_erp_sources_are_synced_periodically(client: httpx.AsyncClient,
                                                   app_engine: AsyncEngine) -> None:
    async with owner(client, "ERP MChJ") as (c, tenant):
        r = await c.post("/api/v1/integrations", headers=csrf(c), json={
            "connector_id": "erp_api", "name": "ERP: Sotuvlar", "entity": "sales.order_line"})
        assert r.status_code == 202, r.text
        erp = r.json()["id"]
        detail = (await c.get(f"/api/v1/integrations/{erp}")).json()
        assert detail["entity"] == "sales.order_line" and detail["status"] == "discovering"
        # Mapping tasdiqlanmagan manba avtomatik sinxronlanmaydi.
        assert (await maintain(client, tenant)).auto_syncs == 0

        async def sync_requests() -> int:
            rows = await sql(app_engine, tenant,
                             "SELECT count(*) FROM integrations.sync_runs WHERE data_source_id = :s",
                             s=UUID(erp))
            return int(rows[0][0])  # type: ignore[index]

        await sql(app_engine, tenant, "UPDATE integrations.data_sources SET status = 'synced',"
                  " mapping_version = 1 WHERE id = :s", s=UUID(erp))
        assert (await maintain(client, tenant)).auto_syncs == 1
        assert await sync_requests() == 1
        assert (await c.get(f"/api/v1/integrations/{erp}")).json()["status"] == "syncing"
        # Sinxron davom etayotganda yoki yaqinda bo‘lgan bo‘lsa — yangi so‘rov yo‘q.
        assert (await maintain(client, tenant)).auto_syncs == 0
        await sql(app_engine, tenant,
                  "UPDATE integrations.data_sources SET status = 'failed' WHERE id = :s",
                  s=UUID(erp))
        assert (await maintain(client, tenant)).auto_syncs == 0
        # Oraliq o‘tgach (standart 15 daqiqa) muvaffaqiyatsiz sinxron ham qayta uriniladi.
        await sql(app_engine, tenant, "UPDATE integrations.sync_runs SET requested_at ="
                  " now() - interval '1 hour' WHERE data_source_id = :s", s=UUID(erp))
        assert (await maintain(client, tenant)).auto_syncs == 1
        assert await sync_requests() == 2
        events = await sql(app_engine, tenant,
                           "SELECT envelope->'payload'->>'connector_id' FROM messaging.outbox"
                           " WHERE event_type = 'SyncSource.v1' AND tenant_id = :t", t=tenant)
        assert [e[0] for e in events] == ["erp_api", "erp_api"]  # type: ignore[index]
        # Qo‘lda: muvaffaqiyatsiz (mapping bor) manbani qayta sinxronlash mumkin.
        await sql(app_engine, tenant,
                  "UPDATE integrations.data_sources SET status = 'failed' WHERE id = :s",
                  s=UUID(erp))
        r = await c.post(f"/api/v1/integrations/{erp}/sync", headers=csrf(c))
        assert r.status_code == 202, r.text


async def test_same_system_cannot_be_connected_twice(client: httpx.AsyncClient) -> None:
    async with owner(client, "Takror MChJ") as (c, _):
        body = {"connector_id": "erp_api", "name": "ERP: Sotuvlar", "entity": "sales.order_line"}
        assert (await c.post("/api/v1/integrations", headers=csrf(c), json=body)).status_code == 202
        again = await c.post("/api/v1/integrations", headers=csrf(c), json=body)
        assert again.status_code == 409 and again.json()["code"] == "ALREADY_CONNECTED"
        assert "ERP: Sotuvlar" in again.json()["message"]
        # Boshqa obyekt (qaytarishlar) — ruxsat; ro‘yxatda analitika holati ham bor.
        other = {**body, "name": "ERP: Qaytarishlar", "entity": "sales.return"}
        assert (await c.post("/api/v1/integrations", headers=csrf(c), json=other)).status_code == 202
        listed = (await c.get("/api/v1/integrations")).json()
        assert {s["name"] for s in listed} == {"ERP: Sotuvlar", "ERP: Qaytarishlar"}
        assert all(s["usage"] is None for s in listed)  # hali yuklanmagan
