"""Load the provided CSV into SQLite and synchronize the Elasticsearch index."""

import ast
import asyncio
import csv
import json
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.repository import DocumentRepository
from app.schemas import DocumentOut
from app.search_backend import ElasticsearchBackend


def read_dataset(path: str) -> list[DocumentOut]:
    documents: list[DocumentOut] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {"text", "created_date", "rubrics"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("CSV должен содержать колонки text, created_date и rubrics")

        for row_number, row in enumerate(reader, start=1):
            text = (row.get("text") or "").strip()
            if not text:
                continue

            raw_rubrics = (row.get("rubrics") or "[]").strip()
            try:
                rubrics = json.loads(raw_rubrics)
            except json.JSONDecodeError:
                rubrics = ast.literal_eval(raw_rubrics)
            if not isinstance(rubrics, list):
                raise ValueError(f"Рубрики в строке {row_number} должны быть массивом")

            raw_date = (row.get("created_date") or "").strip()
            try:
                created_date = datetime.strptime(raw_date, "%Y-%m-%d %H:%M:%S").isoformat(sep=" ")
            except ValueError as error:
                raise ValueError(f"Некорректная дата в строке {row_number}: {raw_date}") from error

            # The supplied CSV has no id column, so its stable row number is the source id.
            documents.append(
                DocumentOut(
                    id=f"post-{row_number:06d}",
                    rubrics=[str(item) for item in rubrics],
                    text=text,
                    created_date=created_date,
                )
            )
    return documents


async def wait_for_elasticsearch(backend: ElasticsearchBackend, attempts: int = 60) -> None:
    for attempt in range(attempts):
        try:
            await backend.client.info()
            return
        except Exception:
            if attempt + 1 == attempts:
                raise
            await asyncio.sleep(2)


async def main() -> None:
    repository = DocumentRepository(settings.database_path)
    backend = ElasticsearchBackend(
        settings.elasticsearch_url,
        settings.elasticsearch_index,
        settings.max_search_candidates,
    )
    try:
        await repository.initialize()
        await wait_for_elasticsearch(backend)
        await backend.ensure_index()

        if await repository.count() == 0:
            documents = read_dataset(settings.dataset_path)
            await repository.upsert_many(documents)
            print(f"Импортировано в SQLite: {len(documents)} документов")

        documents = await repository.all_documents()
        indexed_count = await backend.count()
        if indexed_count < len(documents):
            added = await backend.index_documents(documents)
            print(f"Добавлено в Elasticsearch: {added} документов")
        print(f"Готово. Документов в базе: {await repository.count()}")
    finally:
        await backend.close()


if __name__ == "__main__":
    asyncio.run(main())

