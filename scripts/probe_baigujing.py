"""「白骨精是谁」：第一跳后由 LLM 质检，不足则二次检索落到第 27 回。"""
from __future__ import annotations

import asyncio
import json

from app.services.rag_service import rag_ask

BOOK = "38142d9732a14d4db595337f4abaa924"


async def main() -> None:
    for q in ("白骨精是谁", "尸魔是谁", "白骨夫人是谁"):
        ans = await rag_ask(q, BOOK, chapter_index=None)
        src = [
            (s.get("chapter_index"), (s.get("chapter_title") or "")[:28])
            for s in (ans.get("sources") or [])
        ]
        print(
            json.dumps(
                {
                    "q": q,
                    "sources": src,
                    "has_27": any(i == 26 for i, _ in src),
                    "no_ch13_noise": all(i != 12 for i, _ in src),
                    "answer": (ans.get("answer") or "")[:360],
                },
                ensure_ascii=False,
                indent=2,
            ),
            flush=True,
        )
        print("---", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
