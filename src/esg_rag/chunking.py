from __future__ import annotations

import re
import uuid
from typing import Iterable

from esg_rag.models import Chunk, Document

_SECTION_HEADING = re.compile(
    r"\n(?="
    r"(?:[A-Z][A-Z\s/&-]{3,})"            # UPPERCASE HEADING
    r"|(?:[0-9]+(?:\.[0-9]+)*\.?\s+\S)"    # 1. or 1.2.3 Heading
    r"|(?:#{1,4}\s+\S)"                     # Markdown # / ## / ### / ####
    r"|(?:第[一二三四五六七八九十百千\d]+[章节部分篇条])" # Chinese chapter markers
    r"|(?:[一二三四五六七八九十]+[、.])"     # Chinese numbered lists
    r")"
)

_TABLE_ROW = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)


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
            heading = self._extract_heading(section)
            tables, prose = self._separate_tables(section)

            for table in tables:
                prefix = f"[{heading}] " if heading else ""
                chunks.append(self._make_chunk(
                    f"{prefix}{table}",
                    document.metadata,
                    section_index,
                    0,
                    heading,
                ))

            windows = self._sliding_windows(prose)
            for window_index, window in enumerate(windows):
                if heading and not window.startswith(heading):
                    window = f"[{heading}]\n{window}"
                chunks.append(self._make_chunk(
                    window, document.metadata, section_index, window_index, heading,
                ))
        return chunks

    def _make_chunk(
        self,
        text: str,
        base_metadata: dict,
        section_index: int,
        window_index: int,
        heading: str | None,
    ) -> Chunk:
        metadata = dict(base_metadata)
        metadata["section_index"] = section_index
        metadata["window_index"] = window_index
        if heading:
            metadata["section_heading"] = heading
        return Chunk(chunk_id=str(uuid.uuid4()), text=text, metadata=metadata)

    def _normalize(self, text: str) -> str:
        text = text.replace("\u00a0", " ")
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _split_sections(self, text: str) -> list[str]:
        if not text:
            return []
        blocks = _SECTION_HEADING.split(text)
        return [block.strip() for block in blocks if block.strip()]

    def _extract_heading(self, section: str) -> str | None:
        first_line = section.split("\n", 1)[0].strip()
        cleaned = re.sub(r"^#{1,4}\s+", "", first_line).strip()
        if len(cleaned) > 80 or len(cleaned) < 2:
            return None
        return cleaned

    def _separate_tables(self, section: str) -> tuple[list[str], str]:
        """Pull out contiguous table blocks so they can be indexed as whole units."""
        lines = section.split("\n")
        tables: list[str] = []
        prose_lines: list[str] = []
        current_table: list[str] = []

        for line in lines:
            if _TABLE_ROW.match(line):
                current_table.append(line)
            else:
                if current_table:
                    table_text = "\n".join(current_table)
                    if len(table_text) > 30:
                        tables.append(table_text)
                    else:
                        prose_lines.extend(current_table)
                    current_table = []
                prose_lines.append(line)

        if current_table:
            table_text = "\n".join(current_table)
            if len(table_text) > 30:
                tables.append(table_text)
            else:
                prose_lines.extend(current_table)

        return tables, "\n".join(prose_lines)

    def _sliding_windows(self, text: str) -> list[str]:
        if not text.strip():
            return []
        if len(text) <= self.chunk_size:
            return [text]

        windows: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            candidate = text[start:end]
            if end < len(text):
                split_at = max(
                    candidate.rfind("\n\n"),
                    candidate.rfind(". "),
                    candidate.rfind("。"),
                    candidate.rfind("; "),
                    candidate.rfind("；"),
                )
                if split_at > int(self.chunk_size * 0.4):
                    end = start + split_at + 1
                    candidate = text[start:end]

            windows.append(candidate.strip())
            if end >= len(text):
                break
            start = max(0, end - self.chunk_overlap)
        return windows
