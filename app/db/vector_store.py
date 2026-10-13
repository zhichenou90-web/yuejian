"""Chroma 向量库（按 book_id 过滤）。"""
from __future__ import annotations

import threading

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.core.config import settings
from app.core.logger import setup_logger
from app.services.llm_service import get_embedding_model

logger = setup_logger(__name__)

COLLECTION_NAME = "novel_knowledge_base"
EMBED_BATCH_SIZE = 60

_store: Chroma | None = None
_store_lock = threading.Lock()
# PersistentClient / 底层 sqlite 不宜多线程并发读写
_query_lock = threading.Lock()


def _cosine_distance_to_similarity(distance: float) -> float:
    return max(0.0, min(1.0, 1.0 - distance))


def get_vector_store() -> Chroma:
    global _store
    if _store is not None:
        return _store
    with _store_lock:
        if _store is None:
            _store = Chroma(
                collection_name=COLLECTION_NAME,
                embedding_function=get_embedding_model(),
                persist_directory=str(settings.chroma_dir_path),
                collection_metadata={"hnsw:space": "cosine"},
                relevance_score_fn=_cosine_distance_to_similarity,
            )
        return _store


def add_documents(documents: list[Document]) -> list[str]:
    if not documents:
        return []
    store = get_vector_store()
    all_ids: list[str] = []
    for i in range(0, len(documents), EMBED_BATCH_SIZE):
        batch = documents[i : i + EMBED_BATCH_SIZE]
        with _query_lock:
            ids = store.add_documents(batch)
        all_ids.extend(ids)
        logger.info("已入库 %d/%d 切片", len(all_ids), len(documents))
    return all_ids


def _where(book_id: str | None, chapter_index: int | None) -> dict | None:
    clauses: list[dict] = []
    if book_id:
        clauses.append({"book_id": book_id})
    if chapter_index is not None:
        clauses.append({"chapter_index": int(chapter_index)})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def search_with_score(
    query: str,
    book_id: str | None = None,
    top_k: int | None = None,
    score_threshold: float | None = None,
    chapter_index: int | None = None,
) -> list[tuple[Document, float]]:
    top_k = top_k or settings.retrieval_top_k
    score_threshold = (
        score_threshold
        if score_threshold is not None
        else settings.retrieval_score_threshold
    )
    # Embedding HTTP 可并行；Chroma 本地查询串行，避免 PersistentClient 竞态
    embedding = get_embedding_model().embed_query(query)
    store = get_vector_store()
    with _query_lock:
        results = store.similarity_search_by_vector_with_relevance_scores(
            embedding, k=top_k, filter=_where(book_id, chapter_index)
        )
    filtered = [
        (doc, score) for doc, score in results if score >= score_threshold
    ]
    logger.info(
        "向量检索 query=%r book=%s 命中 %d",
        query[:40],
        book_id,
        len(filtered),
    )
    return filtered


def list_chapter_chunks(book_id: str, chapter_index: int) -> list[Document]:
    """取出某一章的全部切片，按章内顺序排列。"""
    store = get_vector_store()
    coll = store._collection  # noqa: SLF001
    with _query_lock:
        data = coll.get(
            where=_where(book_id, chapter_index),
            include=["documents", "metadatas"],
        )
    docs: list[Document] = []
    for i, text in enumerate(data.get("documents") or []):
        if not text:
            continue
        meta = (data.get("metadatas") or [{}])[i] or {}
        docs.append(Document(page_content=text, metadata=meta))
    docs.sort(key=lambda d: int((d.metadata or {}).get("chunk_in_chapter") or 0))
    return docs


def get_documents_by_book(book_id: str) -> list[Document]:
    store = get_vector_store()
    coll = store._collection  # noqa: SLF001
    with _query_lock:
        data = coll.get(
            where={"book_id": book_id},
            include=["documents", "metadatas"],
        )
    docs: list[Document] = []
    for i, text in enumerate(data.get("documents") or []):
        if text:
            meta = (data.get("metadatas") or [{}])[i] or {}
            docs.append(Document(page_content=text, metadata=meta))
    return docs


def delete_by_book(book_id: str) -> None:
    store = get_vector_store()
    coll = store._collection  # noqa: SLF001
    with _query_lock:
        existing = coll.get(where={"book_id": book_id}, include=[])
        ids = existing.get("ids") or []
        if ids:
            coll.delete(ids=ids)
            logger.info("已删除书籍 %s 的 %d 条向量", book_id, len(ids))
