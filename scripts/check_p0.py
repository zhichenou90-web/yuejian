"""P0 spot check: chapter scope vs global, plus sources."""
from __future__ import annotations

import asyncio
import json

from app.services.rag_service import rag_ask

BOOK = "768d784dc8f14a398facb05d409aed96"


def dump(label: str, payload: dict) -> None:
    print(f"\n=== {label} ===", flush=True)
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)


async def main() -> None:
    local = await rag_ask("这一章刚发生了什么？", BOOK, chapter_index=0)
    dump("local_ch0", {"sources": local["sources"], "answer": local["answer"][:700]})

    global_q = await rag_ask("米彩是谁？", BOOK, chapter_index=0)
    dump(
        "global_micai",
        {"sources": global_q["sources"], "answer": global_q["answer"][:500]},
    )

    missing = await rag_ask("这一章刚发生了什么？", BOOK, chapter_index=None)
    dump("missing_chapter", {"answer": missing["answer"], "sources": missing["sources"]})


if __name__ == "__main__":
    asyncio.run(main())
