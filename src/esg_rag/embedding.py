from __future__ import annotations

import logging
from typing import Iterable

import httpx
import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

from esg_rag.config import Settings

logger = logging.getLogger(__name__)


def _normalize_embeddings(vectors: np.ndarray) -> np.ndarray:
    vectors = vectors.astype(np.float32)
    if vectors.ndim == 1:
        norm = np.linalg.norm(vectors)
        return vectors / max(norm, 1e-9)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-9)


class EmbeddingProvider:
    provider_name = "unknown"

    def embed_documents(self, texts: Iterable[str]) -> np.ndarray:
        raise NotImplementedError

    def embed_query(self, text: str) -> np.ndarray:
        raise NotImplementedError


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    """Uses sentence-transformers for high-quality local semantic embeddings."""

    provider_name = "sentence-transformers"

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading sentence-transformers model: %s", model_name)
        self.model = SentenceTransformer(model_name)
        self.model_name = model_name

    def embed_documents(self, texts: Iterable[str]) -> np.ndarray:
        texts = list(texts)
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        return self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False).astype(
            np.float32
        )

    def embed_query(self, text: str) -> np.ndarray:
        return self.model.encode([text], normalize_embeddings=True, show_progress_bar=False).astype(
            np.float32
        )[0]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    provider_name = "openai"

    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI embeddings.")
        self.settings = settings

    def embed_documents(self, texts: Iterable[str]) -> np.ndarray:
        texts = [text for text in texts if text.strip()]
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        return self._request_embeddings(texts)

    def embed_query(self, text: str) -> np.ndarray:
        return self._request_embeddings([text])[0]

    def _request_embeddings(self, inputs: list[str]) -> np.ndarray:
        payload = {"model": self.settings.openai_embedding_model, "input": inputs}
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.settings.openai_base_url.rstrip('/')}/embeddings"
        timeout = httpx.Timeout(connect=15.0, read=120.0, write=30.0, pool=30.0)
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        data = response.json()["data"]
        vectors = np.array([row["embedding"] for row in data], dtype=np.float32)
        return _normalize_embeddings(vectors)


class HashingEmbeddingProvider(EmbeddingProvider):
    """Fast deterministic fallback that works fully offline."""

    provider_name = "hashing"

    def __init__(self, n_features: int = 1024) -> None:
        self.vectorizer = HashingVectorizer(
            n_features=n_features,
            alternate_sign=False,
            norm="l2",
            ngram_range=(1, 2),
        )

    def embed_documents(self, texts: Iterable[str]) -> np.ndarray:
        texts = list(texts)
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        matrix = self.vectorizer.transform(texts)
        return matrix.astype(np.float32).toarray()

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    backend = settings.embedding_backend.lower()
    if backend == "hash":
        return HashingEmbeddingProvider()
    if backend == "openai":
        try:
            return OpenAIEmbeddingProvider(settings)
        except Exception:
            logger.exception("OpenAI embeddings are unavailable, falling back to local embeddings")
    if backend == "local":
        try:
            return SentenceTransformerEmbeddingProvider(settings.local_embedding_model)
        except Exception:
            logger.exception("Local embeddings are unavailable, falling back to alternate providers")
    if backend not in {"local", "openai", "hash"}:
        raise ValueError(f"Unsupported embedding backend: {settings.embedding_backend}")
    if settings.openai_api_key:
        try:
            return OpenAIEmbeddingProvider(settings)
        except Exception:
            logger.exception("OpenAI embeddings failed during fallback selection")
    return HashingEmbeddingProvider()
