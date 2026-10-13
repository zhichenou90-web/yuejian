"""Live check: generic expansion + early sources, no book-specific query terms."""
from __future__ import annotations

import asyncio
import json
import re

from app.services.rag_service import rag_ask, _expand_retrieval_queries

BOOKS = {
    "女房客": "768d784dc8f14a398facb05d409aed96",
    "三国演义": "1ea9a75cd932407dbfefaf5794b6cea1",
}
FORBIDDEN = ("怀孕", "合租", "留学", "美国", "酒吧", "别这么叫我")


async def main() -> None:
    for q in (
        "昭阳和乐瑶是什么关系？",
        "刘备和关羽什么关系",
        "诸葛亮是谁？",
        "CC的真名是什么？",
    ):
        qs = _expand_retrieval_queries(q)
        bad = [x for x in qs if any(f in x for f in FORBIDDEN)]
        assert not bad, (q, bad)

    rel = await rag_ask("昭阳和乐瑶是什么关系？", BOOKS["女房客"])
    san = await rag_ask("刘备和关羽什么关系", BOOKS["三国演义"])

    def early(src: list) -> list[int]:
        return [
            s["chapter_index"]
            for s in src or []
            if isinstance(s.get("chapter_index"), int)
        ]

    out = {
        "fangke_len": len(rel.get("answer") or ""),
        "fangke_sources": rel.get("sources"),
        "fangke_early": any(i < 40 for i in early(rel.get("sources") or [])),
        "fangke_answer": (rel.get("answer") or "")[:500],
        "sanguo_len": len(san.get("answer") or ""),
        "sanguo_sources": san.get("sources"),
        "sanguo_early": any(i < 40 for i in early(san.get("sources") or [])),
        "sanguo_answer": (san.get("answer") or "")[:500],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    assert out["fangke_len"] < 800, out["fangke_len"]
    assert out["sanguo_len"] < 800, out["sanguo_len"]
    assert out["sanguo_early"] or re.search(r"结义|兄弟", out["sanguo_answer"])
    print("OK live generalize", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
