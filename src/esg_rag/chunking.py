from __future__ import annotations

import re
import uuid
from typing import Iterable

from esg_rag.models import Chunk, Document


class ESGChunker:
    def __init__(self, chunk_size: int = 900, chunk_overlap: int = 150) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_documents(self, documents: Iterable[Document]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for document in documents:
            chunks.extend(self._chunk_document(document))
        return chunks

    def _chunk_document(self, document: Document) -> list[Chunk]:
        normalized = self._normalize(document.text)
        sections = self._split_sections(normalized)
        chunks: list[Chunk] = []

        for section_index, section in enumerate(sections):
            windows = self._sliding_windows(section)
            for window_index, window in enumerate(windows):
                metadata = dict(document.metadata)
                metadata.update({"section_index": section_index, "window_index": window_index})
                chunks.append(
                    Chunk(
                        chunk_id=str(uuid.uuid4()),
                        text=window,
                        metadata=metadata,
                    )
                )
        return chunks

    def _normalize(self, text: str) -> str:
        text = text.replace("\u00a0", " ")
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _split_sections(self, text: str) -> list[str]:
        if not text:
            return []
        blocks = re.split(r"\n(?=(?:[A-Z][A-Z\s/&-]{3,}|[0-9]+\.\s+[A-Z]))", text)
        return [block.strip() for block in blocks if block.strip()]

    def _sliding_windows(self, text: str) -> list[str]:
        if len(text) <= self.chunk_size:
            return [text]

        windows: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            candidate = text[start:end]
            if end < len(text):
                split_at = max(candidate.rfind("\n\n"), candidate.rfind(". "), candidate.rfind("; "))
                if split_at > int(self.chunk_size * 0.5):
                    end = start + split_at + 1
                    candidate = text[start:end]

            windows.append(candidate.strip())
            if end >= len(text):
                break
            start = max(0, end - self.chunk_overlap)
        return windows
