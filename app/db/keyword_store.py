"""BM25 关键词索引（按 book_id 维护）。"""
from __future__ import annotations

import re
import threading

import jieba
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from app.core.logger import setup_logger
from app.db import vector_store as vs

logger = setup_logger(__name__)

_EN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    tokens.extend(_EN_WORD_RE.findall(text))
    tokens.extend(w for w in jieba.cut(text) if w.strip())
    return [t.lower() for t in tokens if t.strip()]


class BookBM25Index:
    """单本书的 BM25 索引。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._bm25: BM25Okapi | None = None
        self._documents: list[Document] = []

    def build(self, documents: list[Document]) -> None:
        with self._lock:
            corpus = [_tokenize(d.page_content) for d in documents]
            self._documents = documents
            self._bm25 = BM25Okapi(corpus) if corpus else None
            logger.info("BM25 构建完成，切片 %d", len(documents))

    def search(
        self,
        query: str,
        top_k: int = 10,
        chapter_index: int | None = None,
    ) -> list[tuple[Document, float]]:
        with self._lock:
            bm25 = self._bm25
            documents = self._documents
        if bm25 is None:
            return []
        tokens = _tokenize(query)
        if not tokens:
            return []
        scores = bm25.get_scores(tokens)
        ranked = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )
        out: list[tuple[Document, float]] = []
        for i in ranked:
            if scores[i] <= 0:
                continue
            doc = documents[i]
            if chapter_index is not None:
                meta_idx = (doc.metadata or {}).get("chapter_index")
                try:
                    if int(meta_idx) != int(chapter_index):
                        continue
                except (TypeError, ValueError):
                    continue
            out.append((doc, float(scores[i])))
            if len(out) >= top_k:
                break
        return out


_indexes: dict[str, BookBM25Index] = {}
_building: dict[str, threading.Event] = {}
_global_lock = threading.Lock()


def rebuild_for_book(book_id: str) -> None:
    docs = vs.get_documents_by_book(book_id)
    idx = BookBM25Index()
    idx.build(docs)
    with _global_lock:
        _indexes[book_id] = idx


def ensure_for_book(book_id: str) -> BookBM25Index:
    """线程安全懒加载：同一 book 只构建一次 BM25。"""
    with _global_lock:
        existing = _indexes.get(book_id)
        if existing is not None:
            return existing
        waiter = _building.get(book_id)
        if waiter is not None:
            event = waiter
            should_build = False
        else:
            event = threading.Event()
            _building[book_id] = event
            should_build = True

    if not should_build:
        event.wait()
        with _global_lock:
            return _indexes[book_id]

    try:
        docs = vs.get_documents_by_book(book_id)
        idx = BookBM25Index()
        idx.build(docs)
        with _global_lock:
            _indexes[book_id] = idx
        return idx
    finally:
        with _global_lock:
            _building.pop(book_id, None)
        event.set()



def keyword_search(
    query: str,
    book_id: str,
    top_k: int = 10,
    chapter_index: int | None = None,
) -> list[tuple[Document, float]]:
    return ensure_for_book(book_id).search(
        query, top_k=top_k, chapter_index=chapter_index
    )


def drop_book_index(book_id: str) -> None:
    with _global_lock:
        _indexes.pop(book_id, None)
