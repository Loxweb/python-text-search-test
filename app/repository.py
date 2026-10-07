import json
from pathlib import Path
from typing import Iterable

import aiosqlite

from app.schemas import DocumentOut


class DocumentRepository:
    """Async SQLite repository for the complete source documents."""

    def __init__(self, database_path: str):
        self.database_path = database_path

    async def initialize(self) -> None:
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    rubrics TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_date TEXT NOT NULL
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_created_date "
                "ON documents(created_date DESC)"
            )
            await db.commit()

    async def upsert_many(self, documents: Iterable[DocumentOut]) -> None:
        rows = [
            (doc.id, json.dumps(doc.rubrics, ensure_ascii=False), doc.text, doc.created_date)
            for doc in documents
        ]
        if not rows:
            return
        async with aiosqlite.connect(self.database_path) as db:
            await db.executemany(
                """
                INSERT INTO documents(id, rubrics, text, created_date)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    rubrics = excluded.rubrics,
                    text = excluded.text,
                    created_date = excluded.created_date
                """,
                rows,
            )
            await db.commit()

    async def get(self, document_id: str) -> DocumentOut | None:
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, rubrics, text, created_date FROM documents WHERE id = ?",
                (document_id,),
            )
            row = await cursor.fetchone()
        return self._from_row(row) if row else None

    async def by_ids_ordered(self, document_ids: list[str], limit: int = 20) -> list[DocumentOut]:
        if not document_ids:
            return []

        # Stay below SQLite's traditional 999 bind-parameter limit and merge each batch.
        found: dict[str, DocumentOut] = {}
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            for start in range(0, len(document_ids), 900):
                batch = document_ids[start : start + 900]
                placeholders = ",".join("?" for _ in batch)
                cursor = await db.execute(
                    "SELECT id, rubrics, text, created_date FROM documents "
                    f"WHERE id IN ({placeholders}) ORDER BY created_date DESC, id ASC LIMIT ?",
                    (*batch, limit),
                )
                for row in await cursor.fetchall():
                    document = self._from_row(row)
                    found[document.id] = document

        return sorted(
            found.values(), key=lambda item: (item.created_date, item.id), reverse=True
        )[:limit]

    async def delete(self, document_id: str) -> bool:
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def count(self) -> int:
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM documents")
            row = await cursor.fetchone()
        return int(row[0])

    async def all_documents(self) -> list[DocumentOut]:
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, rubrics, text, created_date FROM documents ORDER BY id"
            )
            return [self._from_row(row) for row in await cursor.fetchall()]

    @staticmethod
    def _from_row(row: aiosqlite.Row) -> DocumentOut:
        return DocumentOut(
            id=row["id"],
            rubrics=json.loads(row["rubrics"]),
            text=row["text"],
            created_date=row["created_date"],
        )

