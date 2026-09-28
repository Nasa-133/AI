"""Hujjatlar: D01–D05, S03, ACL — haqiqiy Postgres (RLS, FTS) va S3 bilan."""

import hashlib
import zipfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from business.entrypoints.wiring import document_services
from business.platform.db import tenant_transaction
from business.platform.storage import ObjectRef
from tests.unit.documents.samples import make_docx, make_pdf
from tests.unit.identity.fakes import RecordingNotifier

from .test_identity_http import PASSWORD, complete_mfa, csrf, new_client, onboard

pytestmark = pytest.mark.integration


async def upload(c: httpx.AsyncClient, path: Path) -> dict[str, str]:
    with path.open("rb") as f:
        r = await c.post("/api/v1/documents", headers=csrf(c), files={"file": (path.name, f)})
    assert r.status_code == 202, r.text
    return dict(r.json())


async def process(client: httpx.AsyncClient, engine: AsyncEngine, tenant: UUID,
                  doc: dict[str, str]) -> None:
    """Worker o‘rniga: ProcessDocument handler’ini to‘g‘ridan-to‘g‘ri chaqiramiz."""
    container = client._transport.app.state.container  # type: ignore[attr-defined]
    async with tenant_transaction(engine, tenant_id=tenant, user_id=None) as conn:
        await document_services(container, conn, tenant).ingest.process(
            UUID(doc["id"]), UUID(doc["version_id"]))


@asynccontextmanager
async def owner(client: httpx.AsyncClient,
                name: str) -> AsyncIterator[tuple[httpx.AsyncClient, UUID]]:
    async with new_client(client) as c:
        _, body = await onboard(c, name)
        await complete_mfa(c)
        yield c, UUID(body["tenant_id"])


async def test_d01_d02_search_and_sources(client: httpx.AsyncClient, app_engine: AsyncEngine,
                                          tmp_path: Path) -> None:
    async with owner(client, "Hujjat MChJ") as (c, tenant):
        doc = await upload(c, make_docx(tmp_path / "Shartnoma.docx"))
        await process(client, app_engine, tenant, doc)
        detail = (await c.get(f"/api/v1/documents/{doc['id']}")).json()
        assert detail["versions"][0]["parse_status"] == "ready"
        assert detail["versions"][0]["quality"]["sections"] == 6

        found = (await c.post("/api/v1/documents/search", headers=csrf(c),
                              json={"query": "to'lov muddati"})).json()  # ASCII apostrof
        assert found["mode"] == "full_text" and found["notes"]  # AI ulanmagan — matnli rejim
        top = found["results"][0]
        assert top["document_title"] == "Shartnoma" and "15 kun" in top["text"]
        assert "p2" in top["section_ids"] and top["version_no"] == 1  # D01: aniq manba
        section = (await c.get(f"/api/v1/documents/{doc['id']}/versions/{doc['version_id']}"
                               "/sections")).json()
        assert [s["section_id"] for s in section][:3] == ["p1", "p2", "p3"]

        missing = (await c.post("/api/v1/documents/search", headers=csrf(c),
                                json={"query": "sug'urta polisi raqami"})).json()
        assert missing["results"] == []  # D02: uydirma iqtibos yo‘q


async def test_d04_d05_draft_diff_promote_conflict(client: httpx.AsyncClient,
                                                   app_engine: AsyncEngine, tmp_path: Path) -> None:
    async with owner(client, "Tahrir MChJ") as (c, tenant):
        src = make_docx(tmp_path / "Shartnoma.docx")
        original_sha = hashlib.sha256(src.read_bytes()).hexdigest()
        doc = await upload(c, src)
        await process(client, app_engine, tenant, doc)
        base = doc["version_id"]
        draft_body = {"base_version_id": base, "expected_version_id": base, "operations": [
            {"section_id": "p2", "find": "15 kun", "replace": "30 kun"}]}
        r = await c.post(f"/api/v1/documents/{doc['id']}/drafts", headers=csrf(c), json=draft_body)
        assert r.status_code == 201, r.text
        draft = r.json()
        assert [(x["section_id"], x["after"]) for x in draft["changes"]] == [
            ("p2", "To‘lov 30 kun ichida amalga oshiriladi.")]
        second = (await c.post(f"/api/v1/documents/{doc['id']}/drafts", headers=csrf(c),
                               json=draft_body)).json()  # parallel tahrir — ikkinchi draft

        # Original o‘zgarmagan (D04).
        r = await c.get(f"/api/v1/documents/{doc['id']}/versions/{base}/download")
        assert hashlib.sha256(r.content).hexdigest() == original_sha
        d = (await c.get(f"/api/v1/documents/{doc['id']}/diff",
                         params={"left": base, "right": draft["draft_version_id"]})).json()
        assert len(d["changes"]) == 1 and d["unchanged_count"] == 5

        ok = await c.post(f"/api/v1/documents/{doc['id']}/promote", headers=csrf(c), json={
            "version_id": draft["draft_version_id"], "expected_current_version_id": base})
        assert ok.status_code == 200
        # D05: ikkinchi draft eski joriy versiyaga tayangan — yashirin overwrite yo‘q.
        conflict = await c.post(f"/api/v1/documents/{doc['id']}/promote", headers=csrf(c), json={
            "version_id": second["draft_version_id"], "expected_current_version_id": base})
        assert conflict.status_code == 409 and conflict.json()["code"] == "VERSION_CONFLICT"
        stale = await c.post(f"/api/v1/documents/{doc['id']}/drafts", headers=csrf(c),
                             json=draft_body)
        assert stale.status_code == 409

        bad = await c.post(f"/api/v1/documents/{doc['id']}/drafts", headers=csrf(c), json={
            **draft_body, "base_version_id": draft["draft_version_id"],
            "expected_version_id": draft["draft_version_id"],
            "operations": [{"section_id": "p2", "find": "90 kun", "replace": "60 kun"}]})
        assert bad.status_code == 422 and bad.json()["code"] == "PATCH_TARGET_INVALID"


async def test_d03_scanned_pdf_and_rejected_files(client: httpx.AsyncClient,
                                                  app_engine: AsyncEngine, tmp_path: Path) -> None:
    async with owner(client, "Skan MChJ") as (c, tenant):
        doc = await upload(c, make_pdf(tmp_path / "skan.pdf", ["", "", ""]))
        await process(client, app_engine, tenant, doc)
        version = (await c.get(f"/api/v1/documents/{doc['id']}")).json()["versions"][0]
        assert version["parse_status"] == "needs_ocr" and version["quality"]["warnings"]
        search = (await c.post("/api/v1/documents/search", headers=csrf(c),
                               json={"query": "shartnoma"})).json()
        assert search["results"] == []  # bo‘sh fayl “o‘rganildi” deyilmaydi

        macro = make_docx(tmp_path / "makros.docx")
        with zipfile.ZipFile(macro, "a") as z:
            z.writestr("word/vbaProject.bin", b"x")
        with macro.open("rb") as f:
            r = await c.post("/api/v1/documents", headers=csrf(c), files={"file": ("m.docx", f)})
        assert r.status_code == 415 and r.json()["code"] == "DOCUMENT_UNREADABLE"


async def test_acl_and_s03_delete(client: httpx.AsyncClient, app_engine: AsyncEngine,
                                  notifier: RecordingNotifier, tmp_path: Path) -> None:
    async with owner(client, "ACL MChJ") as (c, tenant), new_client(client) as viewer:
        doc = await upload(c, make_docx(tmp_path / "Maxfiy.docx"))
        await process(client, app_engine, tenant, doc)
        await c.put(f"/api/v1/documents/{doc['id']}/access", headers=csrf(c),
                    json={"visibility": "private", "user_ids": []})
        email = f"v-{uuid4().hex[:6]}@demo.uz"
        await c.post("/api/v1/invitations", headers=csrf(c), json={"email": email, "role": "viewer"})
        token = next(t for e, t in notifier.invitations if e == email)
        await viewer.post("/api/v1/invitations/accept", json={"token": token, "password": PASSWORD})
        assert (await viewer.get(f"/api/v1/documents/{doc['id']}")).status_code == 404
        hits = (await viewer.post("/api/v1/documents/search", headers=csrf(viewer),
                                  json={"query": "to'lov"})).json()
        assert hits["results"] == []  # ACL qidiruvdan oldin

        r = await c.delete(f"/api/v1/documents/{doc['id']}", headers=csrf(c))
        assert r.status_code == 202 and r.json()["status"] == "deleting"
        assert (await c.get(f"/api/v1/documents/{doc['id']}")).status_code == 404
        gone = (await c.post("/api/v1/documents/search", headers=csrf(c),
                             json={"query": "to'lov"})).json()
        assert gone["results"] == []  # S03: yangi qidiruvda chiqmaydi

        # S03: tozalash job’i kuzatiladi — fayllar o‘chirilgach “done”.
        job_id = UUID(r.json()["cleanup_job_id"])
        container = client._transport.app.state.container  # type: ignore[attr-defined]
        async with tenant_transaction(app_engine, tenant_id=tenant, user_id=None) as conn:
            services = document_services(container, conn, tenant)
            keys = [(v.bucket, v.object_key) for v in await services.store.versions(UUID(doc["id"]))]
            await services.ingest.cleanup(UUID(doc["id"]), job_id, keys)
            status = (await conn.execute(text(
                "SELECT j.status, d.status FROM documents.cleanup_jobs j JOIN documents.documents d"
                " ON d.id = j.document_id WHERE j.id = :id"), {"id": job_id})).one()
        assert tuple(status) == ("done", "deleted")
        with pytest.raises(Exception):  # noqa: B017 — fayl ombordan haqiqatan o‘chgan
            await container.storage.download_to(
                ObjectRef(keys[0][0], keys[0][1], "0" * 64, 0), tmp_path / "x")


async def test_chat_document_chip_routes_to_assistant_with_context(
        client: httpx.AsyncClient, app_engine: AsyncEngine, tmp_path: Path) -> None:
    async with owner(client, "Chip MChJ") as (c, tenant):
        doc = await upload(c, make_docx(tmp_path / "Shartnoma.docx"))
        await process(client, app_engine, tenant, doc)
        conv = (await c.post("/api/v1/conversations", headers=csrf(c), json={})).json()["id"]
        url = f"/api/v1/conversations/{conv}/messages"
        missing = await c.post(url, headers=csrf(c),
                               json={"content": "Muddat qancha?", "document_ids": [str(uuid4())]})
        assert missing.status_code == 404  # ko‘rinmaydigan hujjat kontekstga qo‘shilmaydi

        r = await c.post(url, headers=csrf(c), json={"content": "To‘lov muddati qancha?",
                                                     "document_ids": [doc["id"]]})
        assert r.status_code == 202 and r.json()["agent_role_key"] == "document_assistant"
        async with tenant_transaction(app_engine, tenant_id=tenant, user_id=None) as conn:
            payload = (await conn.execute(text(
                "SELECT envelope->'payload' FROM messaging.outbox WHERE event_type = 'RunAgent.v1'"
                " AND envelope->'payload'->>'task_id' = :t"), {"t": r.json()["task_id"]})).scalar_one()
        assert payload["context_refs"] == [{"kind": "document_version", "id": doc["id"],
                                            "version_id": doc["version_id"], "locator": None}]
        messages = (await c.get(url)).json()
        assert messages[0]["structured"]["context_documents"][0]["title"] == "Shartnoma"

        # Chip’siz, lekin hujjat so‘zi bilan — ham hujjat yordamchisi.
        r2 = await c.post(url, headers=csrf(c), json={"content": "Shartnomadagi 3-bandni ko‘rsat"})
        assert r2.json()["agent_role_key"] == "document_assistant"


async def test_vector_embeddings_stored_and_searchable(
        client: httpx.AsyncClient, app_engine: AsyncEngine, tmp_path: Path) -> None:
    """App roli pgvector turidan foydalana oladi (0010) va vektor qidiruv ACL doirasida."""
    async with owner(client, "Vektor MChJ") as (c, tenant):
        doc = await upload(c, make_docx(tmp_path / "Shartnoma.docx"))
        await process(client, app_engine, tenant, doc)
        container = client._transport.app.state.container  # type: ignore[attr-defined]
        version = UUID(doc["version_id"])
        async with tenant_transaction(app_engine, tenant_id=tenant, user_id=None) as conn:
            store = document_services(container, conn, tenant).store
            chunks = await store.chunks_of(version)
            vectors = {cid: [1.0 if i == n % 4 else 0.0 for i in range(4)]
                       for n, (cid, _) in enumerate(chunks)}
            assert await store.set_embeddings(version, vectors, "test-4") == len(chunks)
            scope = await store.search_scope(user_id=uuid4(), see_all=True, document_ids=None)
            hits = await store.search_vector(scope, [1.0, 0.0, 0.0, 0.0], 3)
            assert hits and hits[0].chunk_id == chunks[0][0]
            assert await store.search_vector(scope, [1.0] * 8, 3) == []  # boshqa o‘lcham
