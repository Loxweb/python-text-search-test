from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.repository import DocumentRepository
from app.schemas import DeleteResponse, HealthResponse, SearchRequest, SearchResponse
from app.search_backend import ElasticsearchBackend

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


def create_app(repository=None, search_backend=None) -> FastAPI:
    injected_dependencies = repository is not None or search_backend is not None
    repository = repository or DocumentRepository(settings.database_path)
    search_backend = search_backend or ElasticsearchBackend(
        settings.elasticsearch_url,
        settings.elasticsearch_index,
        settings.max_search_candidates,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not injected_dependencies:
            await repository.initialize()
        yield
        if not injected_dependencies:
            await search_backend.close()

    app = FastAPI(
        title="Поиск по документам",
        description=(
            "Асинхронный сервис полнотекстового поиска по документам. "
            "Совпадения ищутся в Elasticsearch, полные записи и рубрики берутся из SQLite."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.repository = repository
    app.state.search_backend = search_backend
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def home():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["Сервис"])
    async def health(request: Request):
        try:
            count = await request.app.state.repository.count()
        except Exception as error:
            logger.exception("Не удалось проверить состояние базы")
            raise HTTPException(status_code=503, detail="База данных недоступна") from error
        return HealthResponse(status="ok", documents=count)

    @app.post("/api/v1/search", response_model=SearchResponse, tags=["Документы"])
    async def search(payload: SearchRequest, request: Request):
        try:
            ids = await request.app.state.search_backend.search_ids(payload.query)
            items = await request.app.state.repository.by_ids_ordered(ids, limit=20)
        except Exception as error:
            logger.exception("Ошибка поиска")
            raise HTTPException(
                status_code=503,
                detail="Поиск временно недоступен. Проверьте, что Elasticsearch запущен.",
            ) from error
        return SearchResponse(query=payload.query, total=len(items), items=items)

    @app.delete(
        "/api/v1/documents/{document_id}",
        response_model=DeleteResponse,
        tags=["Документы"],
    )
    async def delete_document(document_id: str, request: Request):
        repo = request.app.state.repository
        backend = request.app.state.search_backend
        existing = await repo.get(document_id)
        if existing is None:
            # Also clean a possible orphan from the search index.
            try:
                await backend.delete(document_id)
            except Exception as error:
                logger.exception("Не удалось удалить запись из индекса")
                raise HTTPException(status_code=503, detail="Индекс временно недоступен") from error
            raise HTTPException(status_code=404, detail="Документ не найден")

        try:
            await backend.delete(document_id)
            deleted = await repo.delete(document_id)
        except Exception as error:
            # If SQLite fails after Elasticsearch deletion, restore the search entry.
            try:
                await backend.index_documents([existing])
            except Exception:
                logger.exception("Не удалось восстановить документ в индексе после ошибки удаления")
            logger.exception("Ошибка удаления документа %s", document_id)
            raise HTTPException(status_code=503, detail="Не удалось удалить документ") from error
        return DeleteResponse(id=document_id, deleted=deleted)

    return app


app = create_app()

