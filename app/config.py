from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    elasticsearch_url: str = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
    elasticsearch_index: str = os.getenv("ELASTICSEARCH_INDEX", "documents")
    database_path: str = os.getenv("DATABASE_PATH", "./data/search.db")
    dataset_path: str = os.getenv("DATASET_PATH", "./data/posts.csv")
    max_search_candidates: int = int(os.getenv("MAX_SEARCH_CANDIDATES", "10000"))


settings = Settings()

