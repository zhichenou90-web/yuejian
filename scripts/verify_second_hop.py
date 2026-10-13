"""验证「白骨精是谁」是否走二次检索。

用法（在项目根目录）:
  conda run -n novel-rag --no-capture-output python scripts/verify_second_hop.py

会做两件事:
  1) 进程内直接调 prepare_turn / rag_ask（验证当前代码）
  2) 若 8000 端口有服务，再打 HTTP（验证你重启的那个进程）

控制台关键标记:
  [HOOK] 进入 LLM 质检 / 质检结果 / 进入二次检索
  SECOND_HOP=YES|NO  —— 是否真正调用了 _second_hop_retrieve
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

# Windows 控制台避免中文乱码
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BOOK = "38142d9732a14d4db595337f4abaa924"
Q = "白骨精是谁"
API = "http://127.0.0.1:8000"


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        stream=sys.stdout,
        force=True,
    )
    # 只盯二次检索相关 logger，避免刷屏
    for name in (
        "app.services.rag_service",
        "app.services.hybrid_retrieval",
        "app.services.rerank_service",
        "app.db.vector_store",
        "app.db.keyword_store",
    ):
        logging.getLogger(name).setLevel(logging.INFO)


def _dump_sources(label: str, sources: list) -> None:
    print(f"\n===== {label} =====", flush=True)
    idxs = []
    for s in sources or []:
        idx = s.get("chapter_index")
        title = (s.get("chapter_title") or "")[:40]
        idxs.append(idx)
        print(f"  source: ch={idx} title={title}", flush=True)
    print(f"  has_ch27(index=26) = {26 in idxs}", flush=True)
    print(f"  has_ch13(index=12) = {12 in idxs}", flush=True)
    if 12 in idxs and 26 not in idxs:
        print("  !! 仍是第十三回噪声，二次检索未生效或未替换", flush=True)
    elif 26 in idxs:
        print("  OK 已落到第二十七回", flush=True)


async def verify_inprocess() -> None:
    from app.services import rag_service as rs

    print("\n########## 1) 进程内调用（当前磁盘代码） ##########", flush=True)
    print(f"rag_service file = {rs.__file__}", flush=True)
    print(f"has _maybe_second_hop = {hasattr(rs, '_maybe_second_hop')}", flush=True)
    print(f"has _llm_judge_and_plan = {hasattr(rs, '_llm_judge_and_plan')}", flush=True)

    # 包一层，把关键步骤打到控制台
    original_judge = rs._llm_judge_and_plan
    original_second = rs._second_hop_retrieve
    stats = {"judge_calls": 0, "second_hop_calls": 0, "last_can_answer": None}

    async def judge_wrap(*args, **kwargs):
        stats["judge_calls"] += 1
        print("\n>>> [HOOK] 进入 LLM 质检 _llm_judge_and_plan", flush=True)
        plan = await original_judge(*args, **kwargs)
        stats["last_can_answer"] = plan.get("can_answer")
        print(
            ">>> [HOOK] 质检结果 "
            f"can_answer={plan.get('can_answer')} "
            f"reason={plan.get('reason')!r} "
            f"aliases={plan.get('aliases')} "
            f"title_hints={plan.get('title_hints')}",
            flush=True,
        )
        if plan.get("can_answer"):
            print(
                ">>> [HOOK] can_answer=True → 跳过二次检索 "
                "(SECOND_HOP=NO，首轮片段已够答)",
                flush=True,
            )
        else:
            print(
                ">>> [HOOK] can_answer=False → 即将触发二次检索 (SECOND_HOP 待定)",
                flush=True,
            )
        return plan

    async def second_wrap(*args, **kwargs):
        stats["second_hop_calls"] += 1
        print("\n>>> [HOOK] 进入二次检索 _second_hop_retrieve  → SECOND_HOP=YES", flush=True)
        docs = await original_second(*args, **kwargs)
        titles = [
            (
                d.metadata.get("chapter_index"),
                (d.metadata.get("chapter_title") or "")[:28],
            )
            for d, _ in docs
        ]
        print(f">>> [HOOK] 二次检索命中 {len(docs)} 段: {titles}", flush=True)
        return docs

    rs._llm_judge_and_plan = judge_wrap  # type: ignore[assignment]
    rs._second_hop_retrieve = second_wrap  # type: ignore[assignment]

    try:
        print(f"\n--- prepare_turn q={Q!r} chapter_index=None ---", flush=True)
        prepared = await rs.prepare_turn(Q, BOOK, chapter_index=None)
        _dump_sources("prepare_turn.sources", prepared.sources)
        print(
            f"\n>>> SUMMARY prepare_turn: judge_calls={stats['judge_calls']} "
            f"second_hop_calls={stats['second_hop_calls']} "
            f"SECOND_HOP={'YES' if stats['second_hop_calls'] else 'NO'} "
            f"last_can_answer={stats['last_can_answer']}",
            flush=True,
        )

        stats["judge_calls"] = 0
        stats["second_hop_calls"] = 0
        stats["last_can_answer"] = None

        print(f"\n--- rag_ask q={Q!r} ---", flush=True)
        ans = await rs.rag_ask(Q, BOOK, chapter_index=None)
        _dump_sources("rag_ask.sources", ans.get("sources") or [])
        print(
            f"\n>>> SUMMARY rag_ask: judge_calls={stats['judge_calls']} "
            f"second_hop_calls={stats['second_hop_calls']} "
            f"SECOND_HOP={'YES' if stats['second_hop_calls'] else 'NO'} "
            f"last_can_answer={stats['last_can_answer']}",
            flush=True,
        )
        print("\nanswer preview:\n", (ans.get("answer") or "")[:400], flush=True)
    finally:
        rs._llm_judge_and_plan = original_judge  # type: ignore[assignment]
        rs._second_hop_retrieve = original_second  # type: ignore[assignment]


def verify_http() -> None:
    print("\n########## 2) HTTP 调用（你重启的服务） ##########", flush=True)
    try:
        import httpx
    except ImportError:
        print("没有 httpx，跳过 HTTP 检查", flush=True)
        return

    try:
        r = httpx.get(f"{API}/docs", timeout=3.0)
        print(f"GET /docs -> {r.status_code}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"!! 8000 端口无服务或不可达: {exc}", flush=True)
        print("   请确认 uvicorn 已启动，且工作目录是项目根", flush=True)
        return

    payload = {
        "book_id": BOOK,
        "question": Q,
        "history": [],
        "chapter_index": None,
    }
    print(f"POST {API}/api/v1/chat/ask body={payload}", flush=True)
    try:
        r = httpx.post(f"{API}/api/v1/chat/ask", json=payload, timeout=180.0)
        print(f"status={r.status_code}", flush=True)
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        print(f"!! HTTP 问答失败: {exc}", flush=True)
        return

    _dump_sources("HTTP sources", data.get("sources") or [])
    print("\nHTTP answer preview:\n", (data.get("answer") or "")[:400], flush=True)

    # 再打一遍 stream，看事件顺序里有没有二次检索相关 status（若有）
    print("\n--- SSE /api/v1/chat/stream ---", flush=True)
    try:
        with httpx.stream(
            "POST",
            f"{API}/api/v1/chat/stream",
            json=payload,
            timeout=180.0,
        ) as resp:
            print(f"stream status={resp.status_code}", flush=True)
            events = []
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw:
                    continue
                try:
                    evt = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                kind = evt.get("type")
                events.append(kind)
                if kind == "status":
                    print(f"  event status: {evt.get('content')}", flush=True)
                elif kind == "sources":
                    items = evt.get("items") or []
                    _dump_sources("SSE sources", items)
                elif kind == "done":
                    items = evt.get("sources") or []
                    if items:
                        _dump_sources("SSE done.sources", items)
            print(f"  event_order={events}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"!! stream 失败: {exc}", flush=True)


async def main() -> None:
    _setup_logging()
    print("=" * 60, flush=True)
    print("二次检索验证脚本", flush=True)
    print(f"BOOK={BOOK}", flush=True)
    print(f"Q={Q!r}", flush=True)
    print("=" * 60, flush=True)

    await verify_inprocess()
    verify_http()

    print("\n########## 对照说明 ##########", flush=True)
    print(
        "若进程内 OK（有 [HOOK] 质检/二次检索且 ch=26），\n"
        "但 HTTP 仍是 ch=12：说明 8000 上的进程不是这份代码。\n"
        "处理：杀掉占用 8000 的旧 python/uvicorn，再在项目根启动：\n"
        "  conda run -n novel-rag python -m uvicorn app.main:app --host 0.0.0.0 --port 8000",
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
