"""确认流式首包是检索状态，且早于首个 token。"""
from __future__ import annotations

import json
import time

import httpx

BOOK = "768d784dc8f14a398facb05d409aed96"


def main() -> None:
    t0 = time.perf_counter()
    events: list[tuple[str, float]] = []
    with httpx.stream(
        "POST",
        "http://127.0.0.1:8000/api/v1/chat/stream",
        json={
            "book_id": BOOK,
            "question": "刘备是谁？",
            "history": [],
            "chapter_index": None,
        },
        timeout=60,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line.startswith("data:"):
                continue
            evt = json.loads(line[5:].strip())
            kind = evt.get("type", "")
            events.append((kind, time.perf_counter() - t0))
            print(f"{events[-1][1]:6.2f}s {kind} {str(evt.get('content') or '')[:40]}", flush=True)
            if kind == "token" and len([e for e in events if e[0] == "token"]) >= 1:
                break
    kinds = [k for k, _ in events]
    assert kinds[0] == "status", kinds
    status_t = events[0][1]
    token_t = next(t for k, t in events if k == "token")
    assert status_t < 0.8, status_t
    assert status_t < token_t
    print(f"OK status={status_t:.2f}s token={token_t:.2f}s", flush=True)


if __name__ == "__main__":
    main()
