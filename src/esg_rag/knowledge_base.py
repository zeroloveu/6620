from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class KnowledgeBaseManager:
    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _kb_dir(self, kb_id: str) -> Path:
        return self.storage_dir / kb_id

    def _meta_path(self, kb_id: str) -> Path:
        return self._kb_dir(kb_id) / "meta.json"

    def _docs_path(self, kb_id: str) -> Path:
        return self._kb_dir(kb_id) / "docs.json"

    def files_dir(self, kb_id: str) -> Path:
        return self._kb_dir(kb_id) / "files"

    def index_dir(self, kb_id: str) -> Path:
        return self._kb_dir(kb_id) / "index"

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _read_json(path: Path, default=None):
        if not path.exists():
            return default if default is not None else {}
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, data) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _touch_updated(self, kb_id: str) -> None:
        meta_path = self._meta_path(kb_id)
        if meta_path.exists():
            meta = self._read_json(meta_path)
            meta["updated_at"] = self._now()
            self._write_json(meta_path, meta)

    def list_kbs(self) -> list[dict]:
        kbs: list[dict] = []
        if not self.storage_dir.exists():
            return kbs
        for entry in sorted(self.storage_dir.iterdir()):
            if entry.is_dir() and (entry / "meta.json").exists():
                meta = self._read_json(entry / "meta.json")
                docs = self._read_json(entry / "docs.json", [])
                meta["document_count"] = len(docs)
                kbs.append(meta)
        return kbs

    def create_kb(self, name: str, description: str = "") -> dict:
        kb_id = uuid4().hex[:12]
        self._kb_dir(kb_id).mkdir(parents=True, exist_ok=True)
        self.files_dir(kb_id).mkdir(exist_ok=True)
        self.index_dir(kb_id).mkdir(exist_ok=True)
        now = self._now()
        meta = {
            "id": kb_id,
            "name": name,
            "description": description,
            "created_at": now,
            "updated_at": now,
        }
        self._write_json(self._meta_path(kb_id), meta)
        self._write_json(self._docs_path(kb_id), [])
        meta["document_count"] = 0
        return meta

    def get_kb(self, kb_id: str) -> dict | None:
        if not self._meta_path(kb_id).exists():
            return None
        meta = self._read_json(self._meta_path(kb_id))
        docs = self._read_json(self._docs_path(kb_id), [])
        meta["document_count"] = len(docs)
        meta["documents"] = docs
        return meta

    def update_kb(self, kb_id: str, name: str | None = None, description: str | None = None) -> dict | None:
        if not self._meta_path(kb_id).exists():
            return None
        meta = self._read_json(self._meta_path(kb_id))
        if name is not None:
            meta["name"] = name
        if description is not None:
            meta["description"] = description
        meta["updated_at"] = self._now()
        self._write_json(self._meta_path(kb_id), meta)
        docs = self._read_json(self._docs_path(kb_id), [])
        meta["document_count"] = len(docs)
        return meta

    def delete_kb(self, kb_id: str) -> bool:
        kb_dir = self._kb_dir(kb_id)
        if not kb_dir.exists():
            return False
        shutil.rmtree(kb_dir)
        return True

    def list_documents(self, kb_id: str) -> list[dict]:
        return self._read_json(self._docs_path(kb_id), [])

    def add_documents(self, kb_id: str, files: list[tuple[str, bytes]]) -> list[dict]:
        docs = self._read_json(self._docs_path(kb_id), [])
        files_dir = self.files_dir(kb_id)
        files_dir.mkdir(parents=True, exist_ok=True)
        added: list[dict] = []
        for original_name, content in files:
            doc_id = uuid4().hex[:12]
            stored_name = f"{doc_id}_{original_name}"
            (files_dir / stored_name).write_bytes(content)
            doc = {
                "id": doc_id,
                "original_name": original_name,
                "stored_name": stored_name,
                "file_size": len(content),
                "file_type": Path(original_name).suffix.lower().lstrip("."),
                "created_at": self._now(),
            }
            docs.append(doc)
            added.append(doc)
        self._write_json(self._docs_path(kb_id), docs)
        self._touch_updated(kb_id)
        return added

    def delete_document(self, kb_id: str, doc_id: str) -> bool:
        docs = self._read_json(self._docs_path(kb_id), [])
        target = next((d for d in docs if d["id"] == doc_id), None)
        if not target:
            return False
        file_path = self.files_dir(kb_id) / target["stored_name"]
        if file_path.exists():
            file_path.unlink()
        docs = [d for d in docs if d["id"] != doc_id]
        self._write_json(self._docs_path(kb_id), docs)
        self._touch_updated(kb_id)
        return True

    def update_document(self, kb_id: str, doc_id: str, original_name: str | None = None) -> dict | None:
        docs = self._read_json(self._docs_path(kb_id), [])
        target = next((d for d in docs if d["id"] == doc_id), None)
        if not target:
            return None
        if original_name is not None:
            target["original_name"] = original_name
        self._write_json(self._docs_path(kb_id), docs)
        self._touch_updated(kb_id)
        return target
