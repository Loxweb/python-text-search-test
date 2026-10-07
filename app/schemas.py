from pydantic import BaseModel, Field, field_validator


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Поисковый запрос не должен быть пустым")
        return value.strip()


class DocumentOut(BaseModel):
    id: str
    rubrics: list[str]
    text: str
    created_date: str


class SearchResponse(BaseModel):
    query: str
    total: int
    items: list[DocumentOut]


class DeleteResponse(BaseModel):
    id: str
    deleted: bool


class HealthResponse(BaseModel):
    status: str
    documents: int

