from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.repository import DocumentRepository
from app.schemas import DocumentOut


class FakeSearchBackend:
    def __init__(self, ids: list[str]):
        self.ids = ids
        self.deleted: list[str] = []
        self.indexed: list[str] = []

    async def search_ids(self, query: str) -> list[str]:
        assert query
        return list(self.ids)

    async def delete(self, document_id: str) -> None:
        self.deleted.append(document_id)

    async def index_documents(self, documents: list[DocumentOut]) -> int:
        self.indexed.extend(document.id for document in documents)
        return len(documents)


@pytest_asyncio.fixture
async def api(tmp_path):
    repository = DocumentRepository(str(tmp_path / "test.db"))
    await repository.initialize()
    base_date = datetime(2024, 1, 1)
    documents = [
        DocumentOut(
            id=f"doc-{number:02d}",
            rubrics=["news", "тест"],
            text=f"Документ номер {number}",
            created_date=(base_date + timedelta(days=number)).isoformat(sep=" "),
        )
        for number in range(25)
    ]
    await repository.upsert_many(documents)
    backend = FakeSearchBackend([document.id for document in documents])
    app = create_app(repository, backend)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, repository, backend


@pytest.mark.asyncio
async def test_search_returns_full_documents_sorted_newest_first_and_limited_to_20(api):
    client, _, _ = api
    response = await client.post("/api/v1/search", json={"query": "номер"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 20
    assert len(payload["items"]) == 20
    assert payload["items"][0]["id"] == "doc-24"
    assert payload["items"][-1]["id"] == "doc-05"
    assert payload["items"][0]["rubrics"] == ["news", "тест"]
    assert payload["items"][0]["text"] == "Документ номер 24"


@pytest.mark.asyncio
async def test_delete_removes_document_from_sqlite_and_search_index(api):
    client, repository, backend = api
    response = await client.delete("/api/v1/documents/doc-10")

    assert response.status_code == 200
    assert response.json() == {"id": "doc-10", "deleted": True}
    assert await repository.get("doc-10") is None
    assert backend.deleted == ["doc-10"]


@pytest.mark.asyncio
async def test_blank_search_query_is_rejected(api):
    client, _, _ = api
    response = await client.post("/api/v1/search", json={"query": "   "})

    assert response.status_code == 422

