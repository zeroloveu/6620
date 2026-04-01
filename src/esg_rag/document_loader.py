from __future__ import annotations

import json
import logging
from pathlib import Path

from pypdf import PdfReader

from esg_rag.models import Document

logger = logging.getLogger(__name__)


class DocumentLoader:
    supported_extensions = {".txt", ".md", ".pdf", ".json", ".docx"}

    def load_directory(self, directory: Path) -> list[Document]:
        documents: list[Document] = []
        if not directory.exists():
            return documents

        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix.lower() in self.supported_extensions:
                docs = self.load_file(path)
                if docs:
                    logger.info("Loaded %d document(s) from %s", len(docs), path.name)
                else:
                    logger.warning("No content extracted from %s", path.name)
                documents.extend(docs)
        return documents

    def load_file(self, path: Path) -> list[Document]:
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md"}:
            return [
                Document(
                    text=path.read_text(encoding="utf-8", errors="ignore"),
                    metadata=self._base_metadata(path),
                )
            ]
        if suffix == ".json":
            return self._load_json(path)
        if suffix == ".pdf":
            return self._load_pdf(path)
        if suffix == ".docx":
            return self._load_docx(path)
        return []

    def _base_metadata(self, path: Path) -> dict[str, str]:
        return {
            "source": str(path),
            "source_name": path.name,
            "source_type": path.suffix.lower().lstrip("."),
        }

    def _load_json(self, path: Path) -> list[Document]:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        if isinstance(payload, list):
            return [
                Document(
                    text=json.dumps(item, ensure_ascii=False, indent=2),
                    metadata={**self._base_metadata(path), "record_index": index},
                )
                for index, item in enumerate(payload)
            ]
        return [
            Document(
                text=json.dumps(payload, ensure_ascii=False, indent=2),
                metadata=self._base_metadata(path),
            )
        ]

    def _load_pdf(self, path: Path) -> list[Document]:
        if path.stat().st_size == 0:
            logger.warning("Skipping empty file: %s", path.name)
            return []
        try:
            reader = PdfReader(str(path))
        except Exception:
            logger.exception("Failed to open PDF: %s", path.name)
            return []
        documents: list[Document] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                documents.append(
                    Document(
                        text=text,
                        metadata={**self._base_metadata(path), "page": page_number},
                    )
                )
        return documents

    def _load_docx(self, path: Path) -> list[Document]:
        from docx import Document as DocxDocument
        from docx.table import Table

        if path.stat().st_size == 0:
            logger.warning("Skipping empty file: %s", path.name)
            return []

        try:
            doc = DocxDocument(str(path))
        except Exception:
            logger.exception("Failed to open docx: %s", path.name)
            return []

        paragraphs: list[str] = []
        for element in doc.element.body:
            tag = element.tag.split("}")[-1]
            if tag == "p":
                text = element.text or ""
                if text.strip():
                    paragraphs.append(text.strip())
            elif tag == "tbl":
                table = Table(element, doc)
                rows: list[str] = []
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    rows.append(" | ".join(cells))
                if rows:
                    paragraphs.append("\n".join(rows))

        if not paragraphs:
            return []

        chunk_size = 20
        documents: list[Document] = []
        for i in range(0, len(paragraphs), chunk_size):
            batch = paragraphs[i : i + chunk_size]
            text = "\n\n".join(batch)
            if text.strip():
                documents.append(
                    Document(
                        text=text,
                        metadata={
                            **self._base_metadata(path),
                            "section_start": i,
                        },
                    )
                )
        return documents
