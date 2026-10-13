"""开篇关系召回 + 检索耗时抽检。"""
from __future__ import annotations

import asyncio
import json
import re
import time

from app.services.rag_service import _retrieve, rag_ask, wants_early_chapter_bias

BOOK = "768d784dc8f14a398facb05d409aed96"
Q = "昭阳和乐瑶是什么关系？"


async def main() -> None:
    assert wants_early_chapter_bias(Q)

    t0 = time.perf_counter()
    docs = await _retrieve(Q, BOOK)
    t_ret = time.perf_counter() - t0

    idxs: list[int | None] = []
    for d, s in docs:
        idx = d.metadata.get("chapter_index")
        idxs.append(idx if isinstance(idx, int) else None)
        title = d.metadata.get("chapter_title", "")
        preview = (d.page_content or "")[:80]
        print(f"  ch={idx} score={s:.4f} title={title} preview={preview!r}")

    t1 = time.perf_counter()
    ans = await rag_ask(Q, BOOK)
    t_ask = time.perf_counter() - t1
    text = ans.get("answer") or ""
    src_idxs = [
        s.get("chapter_index")
        for s in (ans.get("sources") or [])
        if isinstance(s.get("chapter_index"), int)
    ]

    out = {
        "retrieve_s": round(t_ret, 2),
        "ask_s": round(t_ask, 2),
        "retrieve_idxs": idxs,
        "answer_source_idxs": src_idxs,
        "has_opening_source": any(isinstance(i, int) and i < 12 for i in idxs + src_idxs),
        "has_meet_cue": bool(re.search(r"(怀孕|酒吧|一夜|医院|认识|孩子)", text, re.I)),
        "answer": text[:500],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    assert out["has_opening_source"] or out["has_meet_cue"], "missing opening relationship cue"
    print("OK", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
