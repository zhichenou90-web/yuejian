"""P1: 短答 + 关系题是否带上早期章节。"""
from __future__ import annotations

import asyncio
import json
import re

from app.services.rag_service import rag_ask, wants_early_chapter_bias

BOOK = "768d784dc8f14a398facb05d409aed96"


async def main() -> None:
    assert wants_early_chapter_bias("昭阳和乐瑶是什么关系？")
    assert not wants_early_chapter_bias("米彩是谁？")

    rel = await rag_ask("昭阳和乐瑶是什么关系？", BOOK)
    who = await rag_ask("米彩是谁？", BOOK)

    early_idxs = [
        s["chapter_index"]
        for s in rel.get("sources") or []
        if isinstance(s.get("chapter_index"), int)
    ]
    ans = rel.get("answer") or ""
    who_ans = who.get("answer") or ""

    has_early_fact = bool(
        re.search(r"(怀孕|酒吧|一夜|pao|认识|孩子)", ans, re.I)
    )
    out = {
        "relation_len": len(ans),
        "who_len": len(who_ans),
        "relation_sources": rel.get("sources"),
        "early_source_idxs": early_idxs,
        "has_early_source": any(i < 40 for i in early_idxs),
        "has_early_fact_in_answer": has_early_fact,
        "relation_answer": ans[:600],
        "who_answer": who_ans[:400],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    assert len(ans) < 700, f"relation too long: {len(ans)}"
    assert len(who_ans) < 700, f"who too long: {len(who_ans)}"
    assert out["has_early_source"] or has_early_fact, "missing early relationship cue"
    print("OK", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
