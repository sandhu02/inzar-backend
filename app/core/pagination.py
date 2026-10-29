import base64
import json
from typing import Any, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


def encode_cursor(payload: dict[str, Any]) -> str:
    """Encode cursor payload into a URL-safe base64 string."""
    raw = json.dumps(payload, default=str)
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")


def decode_cursor(cursor: str | None) -> dict[str, Any] | None:
    """Decode a URL-safe base64 string back into cursor payload."""
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        result = json.loads(raw)
        return result if isinstance(result, dict) else None
    except Exception:
        return None


class CursorParams(BaseModel):
    cursor: str | None = Field(default=None, description="Cursor for pagination")
    limit: int = Field(default=20, ge=1, le=100, description="Items per page (max 100)")


class PaginatedResponse[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False
    total_count: int | None = None
