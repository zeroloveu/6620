from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Document:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Chunk:
    chunk_id: str
    text: str
    metadata: dict[str, Any]


@dataclass(slots=True)
class SearchResult:
    chunk_id: str
    score: float
    text: str
    metadata: dict[str, Any]
