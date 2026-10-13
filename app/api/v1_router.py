"""API 路由。"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.core.logger import setup_logger
from app.db import book_store, chat_store
from app.schemas.book_schema import BookInfo, ChapterBrief, ChapterDetail, IngestResult
from app.schemas.qa_schema import BookChatResponse, ChatRequest, ChatResponse, StoredChatMessage
from app.services import ingest_service, rag_service

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["novel-rag"])


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/health")
async def v1_health() -> dict:
    return {"status": "ok"}


@router.get("/books", summary="书库列表")
async def list_books() -> dict:
    books = book_store.list_books()
    return {"code": 0, "books": [BookInfo(**b).model_dump() for b in books]}


@router.post("/books/upload", summary="上传小说并入库")
async def upload_book(file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(400, "缺少文件名")
    suffix = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if suffix != ".txt":
        raise HTTPException(400, "仅支持 .txt 小说文件")
    content = await file.read()
    if not content:
        raise HTTPException(400, "文件为空")
    try:
        result = ingest_service.ingest_novel_bytes(content, file.filename)
    except Exception as exc:  # noqa: BLE001
        logger.exception("入库失败")
        raise HTTPException(500, f"入库失败: {exc}") from exc
    return {"code": 0, "data": IngestResult(**result).model_dump()}


@router.get("/books/{book_id}", summary="书籍详情")
async def get_book(book_id: str) -> dict:
    book = book_store.get_book(book_id)
    if not book:
        raise HTTPException(404, "书籍不存在")
    return {"code": 0, "book": BookInfo(**book).model_dump()}


@router.delete("/books/{book_id}", summary="删除书籍")
async def delete_book(book_id: str) -> dict:
    ok = ingest_service.remove_book(book_id)
    if not ok:
        raise HTTPException(404, "书籍不存在")
    return {"code": 0, "message": "已删除"}


@router.get("/books/{book_id}/chapters", summary="章节目录")
async def list_chapters(book_id: str) -> dict:
    if not book_store.get_book(book_id):
        raise HTTPException(404, "书籍不存在")
    chapters = book_store.list_chapters(book_id)
    return {
        "code": 0,
        "chapters": [ChapterBrief(**c).model_dump() for c in chapters],
    }


@router.get(
    "/books/{book_id}/chapters/{chapter_index}",
    summary="读取某一章",
)
async def get_chapter(book_id: str, chapter_index: int) -> dict:
    ch = book_store.get_chapter(book_id, chapter_index)
    if not ch:
        raise HTTPException(404, "章节不存在")
    book_store.update_reading_progress(book_id, chapter_index)
    return {"code": 0, "chapter": ChapterDetail(**ch).model_dump()}


@router.get("/books/{book_id}/chat", summary="该书问答记录")
async def get_book_chat(book_id: str) -> dict:
    if not book_store.get_book(book_id):
        raise HTTPException(404, "书籍不存在")
    session = chat_store.get_or_create_session(book_id)
    messages = chat_store.list_messages(book_id)
    payload = BookChatResponse(
        session_id=session["id"],
        messages=[StoredChatMessage(**m) for m in messages],
    )
    return {"code": 0, **payload.model_dump()}


@router.delete("/books/{book_id}/chat", summary="清空该书问答记录")
async def clear_book_chat(book_id: str) -> dict:
    if not book_store.get_book(book_id):
        raise HTTPException(404, "书籍不存在")
    chat_store.clear_chat(book_id)
    return {"code": 0, "message": "已清空"}


@router.post("/chat/ask", summary="普通问答")
async def chat_ask(body: ChatRequest) -> ChatResponse:
    if not book_store.get_book(body.book_id):
        raise HTTPException(404, "书籍不存在")
    history = [m.model_dump() for m in body.history]
    result = await rag_service.rag_ask(
        body.question,
        book_id=body.book_id,
        history=history,
        chapter_index=body.chapter_index,
    )
    answer = result["answer"]
    sources = result.get("sources") or []
    try:
        chat_store.append_turn(body.book_id, body.question, answer, sources)
    except Exception:  # noqa: BLE001
        logger.exception("落库问答失败 book=%s", body.book_id)
    return ChatResponse(answer=answer, sources=sources)


@router.post("/chat/stream", summary="SSE 流式问答")
async def chat_stream(body: ChatRequest) -> StreamingResponse:
    if not book_store.get_book(body.book_id):
        raise HTTPException(404, "书籍不存在")
    history = [m.model_dump() for m in body.history]

    async def event_gen():
        parts: list[str] = []
        sources: list[dict] = []
        failed = False
        try:
            # 检索完成前先推状态，避免首字前数秒空白。
            yield _sse({"type": "status", "content": "正在检索原文…"})
            await asyncio.sleep(0)
            async for event in rag_service.rag_stream(
                body.question,
                book_id=body.book_id,
                history=history,
                chapter_index=body.chapter_index,
            ):
                kind = event.get("type")
                if kind == "status":
                    yield _sse({"type": "status", "content": event.get("content") or ""})
                    continue
                if kind == "sources":
                    sources = event.get("items") or []
                    yield _sse({"type": "sources", "items": sources})
                    continue
                token = event.get("content") or ""
                if not token:
                    continue
                parts.append(token)
                yield _sse({"type": "token", "content": token})
            yield _sse({"type": "done", "sources": sources})
        except asyncio.CancelledError:
            answer = "".join(parts).strip()
            if answer:
                try:
                    chat_store.append_turn(
                        body.book_id, body.question, answer, sources
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("中断后落库失败 book=%s", body.book_id)
            raise
        except Exception as exc:  # noqa: BLE001
            failed = True
            logger.exception("流式问答失败")
            yield _sse({"type": "error", "content": str(exc)})
        if not failed:
            answer = "".join(parts)
            try:
                chat_store.append_turn(
                    body.book_id, body.question, answer, sources
                )
            except Exception:  # noqa: BLE001
                logger.exception("落库问答失败 book=%s", body.book_id)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
