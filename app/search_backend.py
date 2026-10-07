from collections.abc import Iterable

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

from app.schemas import DocumentOut


class ElasticsearchBackend:
    def __init__(self, url: str, index_name: str, max_candidates: int = 10_000):
        self.client = AsyncElasticsearch(url, request_timeout=30)
        self.index_name = index_name
        self.max_candidates = max_candidates

    async def ensure_index(self) -> None:
        if await self.client.indices.exists(index=self.index_name):
            return
        await self.client.indices.create(
            index=self.index_name,
            mappings={
                "properties": {
                    "id": {"type": "keyword"},
                    "text": {"type": "text", "analyzer": "russian"},
                }
            },
        )

    async def index_documents(self, documents: Iterable[DocumentOut]) -> int:
        actions = (
            {
                "_op_type": "index",
                "_index": self.index_name,
                "_id": document.id,
                "_source": {"id": document.id, "text": document.text},
            }
            for document in documents
        )
        success, errors = await async_bulk(
            self.client, actions, refresh="wait_for", raise_on_error=False
        )
        if errors:
            raise RuntimeError(f"Elasticsearch не проиндексировал {len(errors)} документов")
        return success

    async def search_ids(self, query: str) -> list[str]:
        response = await self.client.search(
            index=self.index_name,
            body={
                "query": {"match": {"text": {"query": query}}},
                "size": self.max_candidates,
                "_source": ["id"],
            },
        )
        return [hit["_source"]["id"] for hit in response["hits"]["hits"]]

    async def delete(self, document_id: str) -> None:
        await self.client.options(ignore_status=404).delete(
            index=self.index_name, id=document_id
        )

    async def count(self) -> int:
        response = await self.client.count(index=self.index_name)
        return int(response["count"])

    async def close(self) -> None:
        await self.client.close()

