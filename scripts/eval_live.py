"""Live RAG eval — temporary runner for product review."""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
BOOKS = {
    "女房客": "768d784dc8f14a398facb05d409aed96",
    "三国演义": "1ea9a75cd932407dbfefaf5794b6cea1",
    "西游记": "38142d9732a14d4db595337f4abaa924",
}

CASES = [
    {
        "id": "F1",
        "book": "女房客",
        "q": "米彩是谁？",
        "expect": "买房女人/合租相关",
        "cat": "人物",
    },
    {
        "id": "F2",
        "book": "女房客",
        "q": "昭阳和乐瑶是什么关系？",
        "expect": "酒吧认识/一夜情/怀孕纠葛",
        "cat": "关系",
    },
    {
        "id": "F3",
        "book": "女房客",
        "q": "CC是谁？",
        "expect": "音乐餐厅老板娘/重庆姑娘",
        "cat": "人物",
    },
    {
        "id": "F4",
        "book": "女房客",
        "q": "蔚然是谁？",
        "expect": "米彩的朋友/男",
        "cat": "人物",
    },
    {
        "id": "F5",
        "book": "女房客",
        "q": "这一章刚发生了什么？",
        "expect": "应承认缺当前章上下文或泛答",
        "cat": "当前章",
    },
    {
        "id": "S1",
        "book": "三国演义",
        "q": "刘备桃园结义的结拜兄弟是谁？",
        "expect": "关羽、张飞",
        "cat": "情节",
    },
    {
        "id": "S2",
        "book": "三国演义",
        "q": "诸葛亮是谁？",
        "expect": "刘备军师/卧龙",
        "cat": "人物",
    },
    {
        "id": "X1",
        "book": "西游记",
        "q": "孙悟空的师傅是谁？",
        "expect": "菩提祖师或唐僧，须合理",
        "cat": "人物",
    },
    {
        "id": "X2",
        "book": "西游记",
        "q": "唐僧有几个徒弟？分别叫什么？",
        "expect": "三个：悟空、八戒、沙僧",
        "cat": "情节",
    },
]


def ask(book_id: str, question: str, history=None, timeout: float = 180.0):
    t0 = time.perf_counter()
    r = httpx.post(
        f"{BASE}/api/v1/chat/ask",
        json={
            "book_id": book_id,
            "question": question,
            "history": history or [],
        },
        timeout=timeout,
    )
    dt = time.perf_counter() - t0
    r.raise_for_status()
    data = r.json()
    return data.get("answer", ""), dt


def stream_ttfb(book_id: str, question: str, timeout: float = 180.0):
    t0 = time.perf_counter()
    ttfb = None
    parts: list[str] = []
    with httpx.stream(
        "POST",
        f"{BASE}/api/v1/chat/stream",
        json={"book_id": book_id, "question": question, "history": []},
        timeout=timeout,
    ) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw:
                continue
            evt = json.loads(raw)
            if evt.get("type") == "token":
                if ttfb is None:
                    ttfb = time.perf_counter() - t0
                parts.append(evt.get("content") or "")
            elif evt.get("type") in ("done", "error"):
                break
    total = time.perf_counter() - t0
    return "".join(parts), ttfb, total


def main() -> None:
    health = httpx.get(f"{BASE}/api/v1/health", timeout=10).json()
    print("health:", health, flush=True)

    results: list[dict] = []
    for case in CASES:
        bid = BOOKS[case["book"]]
        print(f"\n=== {case['id']} [{case['book']}] {case['q']} ===", flush=True)
        try:
            ans, dt = ask(bid, case["q"])
            print(f"latency={dt:.1f}s len={len(ans)}", flush=True)
            print(ans[:800], flush=True)
            results.append(
                {
                    **case,
                    "ok": True,
                    "latency_s": round(dt, 2),
                    "answer": ans,
                }
            )
        except Exception as e:  # noqa: BLE001
            print("FAIL", e, flush=True)
            results.append({**case, "ok": False, "error": str(e), "answer": ""})

    print("\n=== POLLUTION: 乐瑶 -> 蔚然 ===", flush=True)
    bid = BOOKS["女房客"]
    try:
        a1, d1 = ask(bid, "乐瑶是谁？")
        hist = [
            {"role": "user", "content": "乐瑶是谁？"},
            {"role": "assistant", "content": a1},
        ]
        a2, d2 = ask(bid, "蔚然是谁？", history=hist)
        print(f"seed latency={d1:.1f}s", flush=True)
        print(a1[:400], flush=True)
        print(f"target latency={d2:.1f}s", flush=True)
        print(a2[:800], flush=True)
        results.append(
            {
                "id": "P1",
                "book": "女房客",
                "q": "乐瑶是谁？ -> 蔚然是谁？",
                "cat": "历史串题",
                "ok": True,
                "latency_s": round(d1 + d2, 2),
                "answer": f"[乐瑶]\n{a1}\n\n[蔚然]\n{a2}",
                "seed": a1,
                "target": a2,
            }
        )
    except Exception as e:  # noqa: BLE001
        print("FAIL", e, flush=True)
        results.append({"id": "P1", "ok": False, "error": str(e), "answer": ""})

    print("\n=== STREAM TTFB ===", flush=True)
    try:
        ans, ttfb, total = stream_ttfb(BOOKS["三国演义"], "关羽和刘备是什么关系？")
        print(f"ttfb={ttfb:.1f}s total={total:.1f}s", flush=True)
        print(ans[:500], flush=True)
        results.append(
            {
                "id": "T1",
                "book": "三国演义",
                "q": "关羽和刘备是什么关系？",
                "cat": "流式延迟",
                "ok": True,
                "ttfb_s": round(ttfb or -1, 2),
                "latency_s": round(total, 2),
                "answer": ans,
            }
        )
    except Exception as e:  # noqa: BLE001
        print("FAIL", e, flush=True)
        results.append({"id": "T1", "ok": False, "error": str(e), "answer": ""})

    out = Path("data/eval_live_results.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nSaved", out, "cases=", len(results), flush=True)


if __name__ == "__main__":
    main()
