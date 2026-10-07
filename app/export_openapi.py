"""Export the FastAPI-generated OpenAPI document to docs.json."""

import json
from pathlib import Path

from app.main import app


destination = Path(__file__).resolve().parent.parent / "docs.json"
destination.write_text(
    json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(f"OpenAPI документация сохранена: {destination}")

