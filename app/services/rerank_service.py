"""智谱 Rerank。"""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger(__name__)

RERANK_URL = "https://open.bigmodel.cn/api/paas/v4/rerank"
RERANK_MODEL = "rerank"


async def rerank(
    query: str, documents: list[str], top_n: int | None = None
) -> list[dict]:
    if not documents:
        return []

    payload: dict = {
        "model": RERANK_MODEL,
        "query": query,
        "documents": documents,
    }
    if top_n:
        payload["top_n"] = top_n

    headers = {
        "Authorization": f"Bearer {settings.embedding_api_key_resolved}"
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(RERANK_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        results = data.get("results", [])
        for item in results:
            idx = item.get("index")
            if idx is not None and idx < len(documents):
                item["text"] = documents[idx]
        logger.info(
            "Rerank 完成: 候选 %d -> %d", len(documents), len(results)
        )
        return results
    except Exception as exc:  # noqa: BLE001
        logger.error("Rerank 失败，回退原序: %s", exc)
        return [
            {"index": i, "relevance_score": 0.0, "text": doc}
            for i, doc in enumerate(documents[: top_n or len(documents)])
        ]
