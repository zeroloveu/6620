from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_chat_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_CHAT_MODEL")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL"
    )
    embedding_backend: str = Field(default="local", alias="EMBEDDING_BACKEND")
    local_embedding_model: str = Field(
        default="all-MiniLM-L6-v2", alias="LOCAL_EMBEDDING_MODEL"
    )

    kb_storage_dir: Path = Field(default=Path("./storage/kbs"), alias="KB_STORAGE_DIR")

    data_dir: Path = Field(default=Path("./data"), alias="DATA_DIR")
    index_dir: Path = Field(default=Path("./storage/index"), alias="INDEX_DIR")
    upload_dir: Path = Field(default=Path("./data/uploads"), alias="UPLOAD_DIR")
    vector_backend: str = Field(default="simple", alias="VECTOR_BACKEND")
    chroma_collection: str = Field(default="esg_documents", alias="CHROMA_COLLECTION")
    milvus_uri: str = Field(default="./storage/milvus_esg.db", alias="MILVUS_URI")
    milvus_collection: str = Field(default="esg_documents", alias="MILVUS_COLLECTION")
    chunk_size: int = Field(default=900, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=150, alias="CHUNK_OVERLAP")
    top_k: int = Field(default=6, alias="TOP_K")
    max_context_chunks: int = Field(default=8, alias="MAX_CONTEXT_CHUNKS")
    retrieval_candidate_multiplier: int = Field(default=4, alias="RETRIEVAL_CANDIDATE_MULTIPLIER")


settings = Settings()
