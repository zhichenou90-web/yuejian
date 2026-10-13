"""全链路实测：经 HTTP API 覆盖人物/关系/当前章/串题/流式/跨书。"""
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
        "expect": "女总裁/恋人/买房相关皆可，须有依据",
        "cat": "人物",
        "chapter_index": None,
    },
    {
        "id": "F2",
        "book": "女房客",
        "q": "昭阳和乐瑶是什么关系？",
        "expect": "应提到初始纠葛或多年情谊，不宜只答后期签约",
        "cat": "关系",
        "chapter_index": None,
    },
    {
        "id": "F3",
        "book": "女房客",
        "q": "CC是谁？",
        "expect": "空城里/音乐餐厅相关，勿瞎编真名",
        "cat": "人物",
        "chapter_index": None,
    },
    {
        "id": "F4",
        "book": "女房客",
        "q": "蔚然是谁？",
        "expect": "米彩追求者/投资方/情敌",
        "cat": "人物",
        "chapter_index": None,
    },
    {
        "id": "F5a",
        "book": "女房客",
        "q": "这一章刚发生了什么？",
        "expect": "无章节时应提示先打开章节",
        "cat": "当前章-无上下文",
        "chapter_index": None,
    },
    {
        "id": "F5b",
        "book": "女房客",
        "q": "这一章刚发生了什么？",
        "expect": "应落在第1章医院怀孕场景，勿扯504章",
        "cat": "当前章-有上下文",
        "chapter_index": 0,
    },
    {
        "id": "F6",
        "book": "女房客",
        "q": "后面米彩和昭阳会怎样？",
        "expect": "全书回顾/剧透应可答，不因当前章受限",
        "cat": "剧透全局",
        "chapter_index": 0,
    },
    {
        "id": "S1",
        "book": "三国演义",
        "q": "刘备桃园结义的结拜兄弟是谁？",
        "expect": "关羽、张飞",
        "cat": "情节",
        "chapter_index": None,
    },
    {
        "id": "S2",
        "book": "三国演义",
        "q": "诸葛亮是谁？",
        "expect": "孔明/卧龙/军师",
        "cat": "人物",
        "chapter_index": None,
    },
    {
        "id": "S3",
        "book": "三国演义",
        "q": "刘备和关羽什么关系？",
        "expect": "结义兄弟，出处宜含早期回",
        "cat": "关系",
        "chapter_index": None,
    },
    {
        "id": "X1",
        "book": "西游记",
        "q": "孙悟空的师傅是谁？",
        "expect": "唐僧或菩提，须说明依据范围",
        "cat": "人物",
        "chapter_index": None,
    },
    {
        "id": "X2",
        "book": "西游记",
        "q": "唐僧有几个徒弟？分别叫什么？",
        "expect": "悟空、八戒、沙僧",
        "cat": "情节",
        "chapter_index": None,
    },
]


def ask(
    book_id: str,
    question: str,
    history=None,
    chapter_index=None,
    timeout: float = 180.0,
):
    t0 = time.perf_counter()
    r = httpx.post(
        f"{BASE}/api/v1/chat/ask",
        json={
            "book_id": book_id,
            "question": question,
            "history": history or [],
            "chapter_index": chapter_index,
        },
        timeout=timeout,
    )
    dt = time.perf_counter() - t0
    r.raise_for_status()
    data = r.json()
    return data.get("answer", ""), data.get("sources") or [], dt


def stream_probe(book_id: str, question: str, timeout: float = 120.0):
    t0 = time.perf_counter()
    kinds: list[tuple[str, float]] = []
    answer_parts: list[str] = []
    sources: list = []
    with httpx.stream(
        "POST",
        f"{BASE}/api/v1/chat/stream",
        json={
            "book_id": book_id,
            "question": question,
            "history": [],
            "chapter_index": None,
        },
        timeout=timeout,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line.startswith("data:"):
                continue
            evt = json.loads(line[5:].strip())
            kind = evt.get("type", "")
            kinds.append((kind, time.perf_counter() - t0))
            if kind == "token":
                answer_parts.append(evt.get("content") or "")
            elif kind == "sources":
                sources = evt.get("items") or []
            elif kind in ("done", "error"):
                break
    return {
        "event_order": [k for k, _ in kinds[:6]],
        "status_t": next((t for k, t in kinds if k == "status"), None),
        "ttfb": next((t for k, t in kinds if k == "token"), None),
        "total": time.perf_counter() - t0,
        "answer": "".join(answer_parts)[:400],
        "sources": sources,
    }


def main() -> None:
    health = httpx.get(f"{BASE}/api/v1/health", timeout=10).json()
    print("health:", health, flush=True)

    results: list[dict] = []
    for case in CASES:
        bid = BOOKS[case["book"]]
        print(
            f"\n=== {case['id']} [{case['book']}] ch={case['chapter_index']} {case['q']} ===",
            flush=True,
        )
        try:
            ans, sources, dt = ask(
                bid, case["q"], chapter_index=case["chapter_index"]
            )
            print(f"latency={dt:.1f}s len={len(ans)} sources={len(sources)}", flush=True)
            print(ans[:700], flush=True)
            if sources:
                print(
                    "sources:",
                    [
                        f"{s.get('chapter_index')}:{s.get('chapter_title')}"
                        for s in sources[:4]
                    ],
                    flush=True,
                )
            results.append(
                {
                    **case,
                    "ok": True,
                    "latency_s": round(dt, 2),
                    "answer": ans,
                    "sources": sources,
                    "answer_len": len(ans),
                }
            )
        except Exception as e:  # noqa: BLE001
            print("FAIL", e, flush=True)
            results.append({**case, "ok": False, "error": str(e), "answer": ""})

    print("\n=== POLLUTION 乐瑶 -> 蔚然 ===", flush=True)
    bid = BOOKS["女房客"]
    try:
        a1, s1, d1 = ask(bid, "乐瑶是谁？")
        hist = [
            {"role": "user", "content": "乐瑶是谁？"},
            {"role": "assistant", "content": a1},
        ]
        a2, s2, d2 = ask(bid, "蔚然是谁？", history=hist)
        print(f"seed {d1:.1f}s / target {d2:.1f}s", flush=True)
        print("[蔚然]", a2[:500], flush=True)
        results.append(
            {
                "id": "P1",
                "book": "女房客",
                "q": "乐瑶是谁？ -> 蔚然是谁？",
                "cat": "历史串题",
                "ok": True,
                "latency_s": round(d1 + d2, 2),
                "answer": a2,
                "seed": a1,
                "sources": s2,
                "answer_len": len(a2),
            }
        )
    except Exception as e:  # noqa: BLE001
        print("FAIL", e, flush=True)
        results.append({"id": "P1", "ok": False, "error": str(e), "answer": ""})

    print("\n=== STREAM TTFB ===", flush=True)
    try:
        probe = stream_probe(BOOKS["三国演义"], "关羽和刘备是什么关系？")
        print(probe, flush=True)
        results.append({"id": "T1", "cat": "流式体验", "ok": True, **probe})
    except Exception as e:  # noqa: BLE001
        print("FAIL", e, flush=True)
        results.append({"id": "T1", "ok": False, "error": str(e)})

    out = Path("data/eval_full_results.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nSaved", out, "n=", len(results), flush=True)


if __name__ == "__main__":
    main()
