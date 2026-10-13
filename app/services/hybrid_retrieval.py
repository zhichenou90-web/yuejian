"""混合检索：向量 + BM25，RRF 融合。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from langchain_core.documents import Document

from app.core.config import settings
from app.core.logger import setup_logger
from app.db.keyword_store import keyword_search
from app.db.vector_store import search_with_score

logger = setup_logger(__name__)
RRF_K = 60.0


def _token_key(doc: Document) -> str:
    return doc.page_content[:200]


def _rrf_fuse(
    vector_results: list[tuple[Document, float]],
    keyword_results: list[tuple[Document, float]],
    top_k: int,
) -> list[tuple[Document, float]]:
    fused: dict[str, dict] = {}

    def add_rank(items: list[tuple[Document, float]]) -> None:
        for rank, (doc, _) in enumerate(items, start=1):
            key = _token_key(doc)
            if key not in fused:
                fused[key] = {"doc": doc, "rrf": 0.0}
            fused[key]["rrf"] += 1.0 / (RRF_K + rank)

    add_rank(vector_results)
    add_rank(keyword_results)
    sorted_items = sorted(
        fused.values(), key=lambda x: x["rrf"], reverse=True
    )[:top_k]
    return [(item["doc"], item["rrf"]) for item in sorted_items]


def hybrid_search(
    query: str,
    book_id: str,
    top_k: int | None = None,
    chapter_index: int | None = None,
    score_threshold: float | None = None,
) -> list[tuple[Document, float]]:
    top_k = top_k or settings.retrieval_top_k
    with ThreadPoolExecutor(max_workers=2) as pool:
        vec_fut = pool.submit(
            search_with_score,
            query,
            book_id=book_id,
            top_k=top_k * 2,
            chapter_index=chapter_index,
            score_threshold=score_threshold,
        )
        kw_fut = pool.submit(
            keyword_search,
            query,
            book_id=book_id,
            top_k=top_k * 2,
            chapter_index=chapter_index,
        )
        vector_results = vec_fut.result()
        keyword_results = kw_fut.result()
    fused = _rrf_fuse(vector_results, keyword_results, top_k=top_k)
    logger.info(
        "混合检索: 向量%d + 关键词%d -> %d",
        len(vector_results),
        len(keyword_results),
        len(fused),
    )
    return fused
