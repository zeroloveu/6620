from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import joblib
import numpy as np

from esg_rag.config import Settings
from esg_rag.models import Chunk, SearchResult


class VectorStore(Protocol):
    def index(self, chunks: list[Chunk], embeddings: np.ndarray) -> None: ...

    def search(self, query_vector: np.ndarray, top_k: int = 6) -> list[SearchResult]: ...

    def stats(self) -> dict[str, object]: ...


class SimpleVectorStore:
    def __init__(self, persist_dir: Path) -> None:
        self.persist_dir = persist_dir
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.matrix_path = self.persist_dir / "vectors.npy"
        self.meta_path = self.persist_dir / "chunks.json"
        self.vectors: np.ndarray | None = None
        self.chunks: list[Chunk] = []
        self._load()

    def index(self, chunks: list[Chunk], embeddings: np.ndarray) -> None:
        self.chunks = chunks
        self.vectors = embeddings.astype(np.float32)
        np.save(self.matrix_path, self.vectors)
        payload = [
            {"chunk_id": chunk.chunk_id, "text": chunk.text, "metadata": chunk.metadata}
            for chunk in chunks
        ]
        self.meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        joblib.dump({"count": len(chunks)}, self.persist_dir / "state.joblib")

    def search(self, query_vector: np.ndarray, top_k: int = 6) -> list[SearchResult]:
        if self.vectors is None or len(self.chunks) == 0:
            return []
        query = query_vector.astype(np.float32)
        norms = np.linalg.norm(self.vectors, axis=1) * max(np.linalg.norm(query), 1e-9)
        scores = (self.vectors @ query) / np.maximum(norms, 1e-9)
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [
            SearchResult(
                chunk_id=self.chunks[int(index)].chunk_id,
                score=float(scores[index]),
                text=self.chunks[int(index)].text,
                metadata=self.chunks[int(index)].metadata,
            )
            for index in top_indices
        ]

    def clear(self) -> None:
        """Remove all indexed data so stale entries don't survive a re-index."""
        self.vectors = None
        self.chunks = []
        if self.matrix_path.exists():
            self.matrix_path.unlink()
        if self.meta_path.exists():
            self.meta_path.unlink()
        state_path = self.persist_dir / "state.joblib"
        if state_path.exists():
            state_path.unlink()

    def _load(self) -> None:
        if self.matrix_path.exists() and self.meta_path.exists():
            self.vectors = np.load(self.matrix_path)
            payload = json.loads(self.meta_path.read_text(encoding="utf-8"))
            self.chunks = [
                Chunk(chunk_id=item["chunk_id"], text=item["text"], metadata=item["metadata"])
                for item in payload
            ]

    def stats(self) -> dict[str, object]:
        return {
            "chunk_count": len(self.chunks),
            "source_count": len({item.metadata.get("source") for item in self.chunks if item.metadata.get("source")}),
            "source_preview": sorted(
                {
                    item.metadata.get("source_name", item.metadata.get("source"))
                    for item in self.chunks
                    if item.metadata.get("source")
                }
            )[:6],
        }


class ChromaVectorStore:
    def __init__(self, persist_dir: Path, collection_name: str) -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError(
                "Chroma backend requires the optional dependency: pip install -e .[vectordb]"
            ) from exc

        self.client = chromadb.PersistentClient(path=str(persist_dir / "chroma"))
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def index(self, chunks: list[Chunk], embeddings: np.ndarray) -> None:
        self.collection.delete(where={})
        if not chunks:
            return
        self.collection.add(
            ids=[chunk.chunk_id for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            embeddings=embeddings.tolist(),
            metadatas=[self._stringify_metadata(chunk.metadata) for chunk in chunks],
        )

    def search(self, query_vector: np.ndarray, top_k: int = 6) -> list[SearchResult]:
        payload = self.collection.query(
            query_embeddings=[query_vector.tolist()],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        documents = payload.get("documents", [[]])[0]
        metadatas = payload.get("metadatas", [[]])[0]
        distances = payload.get("distances", [[]])[0]
        ids = payload.get("ids", [[]])[0]
        results: list[SearchResult] = []
        for chunk_id, text, metadata, distance in zip(ids, documents, metadatas, distances, strict=False):
            score = 1.0 / (1.0 + float(distance))
            results.append(
                SearchResult(
                    chunk_id=chunk_id,
                    score=score,
                    text=text,
                    metadata=self._restore_metadata(metadata),
                )
            )
        return results

    def _stringify_metadata(self, metadata: dict) -> dict:
        serialized: dict[str, str | int | float | bool] = {}
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool)):
                serialized[key] = value
            else:
                serialized[key] = json.dumps(value, ensure_ascii=False)
        return serialized

    def _restore_metadata(self, metadata: dict) -> dict:
        restored: dict = {}
        for key, value in metadata.items():
            if not isinstance(value, str):
                restored[key] = value
                continue
            try:
                restored[key] = json.loads(value)
            except json.JSONDecodeError:
                restored[key] = value
        return restored

    def stats(self) -> dict[str, object]:
        return {
            "chunk_count": self.collection.count(),
            "source_count": None,
            "source_preview": [],
        }


class MilvusVectorStore:
    def __init__(self, uri: str, collection_name: str, dimension: int | None = None) -> None:
        try:
            from pymilvus import MilvusClient
        except ImportError as exc:
            raise RuntimeError(
                "Milvus backend requires the optional dependency: pip install -e .[vectordb]"
            ) from exc
        self.uri = uri
        self.collection_name = collection_name
        self.dimension = dimension
        self.client = MilvusClient(uri=uri)

    def index(self, chunks: list[Chunk], embeddings: np.ndarray) -> None:
        if chunks and (self.dimension is None or self.dimension != int(embeddings.shape[1])):
            self.dimension = int(embeddings.shape[1])
            self._recreate_collection()
        if not chunks:
            return
        rows = []
        for chunk, embedding in zip(chunks, embeddings, strict=False):
            rows.append(
                {
                    "id": chunk.chunk_id,
                    "vector": embedding.tolist(),
                    "text": chunk.text,
                    "metadata": json.dumps(chunk.metadata, ensure_ascii=False),
                }
            )
        self.client.delete(collection_name=self.collection_name, filter="id != ''")
        self.client.insert(collection_name=self.collection_name, data=rows)

    def search(self, query_vector: np.ndarray, top_k: int = 6) -> list[SearchResult]:
        payload = self.client.search(
            collection_name=self.collection_name,
            data=[query_vector.tolist()],
            limit=top_k,
            output_fields=["text", "metadata"],
        )
        results: list[SearchResult] = []
        for item in payload[0]:
            entity = item["entity"]
            results.append(
                SearchResult(
                    chunk_id=str(entity["id"]),
                    score=float(item["distance"]),
                    text=entity["text"],
                    metadata=json.loads(entity["metadata"]),
                )
            )
        return results

    def _recreate_collection(self) -> None:
        if self.client.has_collection(collection_name=self.collection_name):
            self.client.drop_collection(collection_name=self.collection_name)
        self.client.create_collection(
            collection_name=self.collection_name,
            dimension=self.dimension,
            primary_field_name="id",
            id_type="string",
            vector_field_name="vector",
            metric_type="COSINE",
            auto_id=False,
            schema={
                "fields": [
                    {"name": "id", "type": "varchar", "is_primary": True, "max_length": 128},
                    {"name": "vector", "type": "float_vector", "params": {"dim": self.dimension}},
                    {"name": "text", "type": "varchar", "max_length": 65535},
                    {"name": "metadata", "type": "varchar", "max_length": 65535},
                ]
            },
        )

    def stats(self) -> dict[str, object]:
        try:
            chunk_count = self.client.get_collection_stats(collection_name=self.collection_name).get("row_count")
        except Exception:
            chunk_count = None
        return {
            "chunk_count": int(chunk_count) if chunk_count is not None else None,
            "source_count": None,
            "source_preview": [],
        }


def build_vector_store(settings: Settings, embedding_dim: int | None = None) -> VectorStore:
    backend = settings.vector_backend.lower()
    if backend == "simple":
        return SimpleVectorStore(settings.index_dir)
    if backend == "chroma":
        return ChromaVectorStore(settings.index_dir, settings.chroma_collection)
    if backend == "milvus":
        return MilvusVectorStore(settings.milvus_uri, settings.milvus_collection, embedding_dim)
    raise ValueError(f"Unsupported vector backend: {settings.vector_backend}")
