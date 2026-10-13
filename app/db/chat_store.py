"""按书一条会话的聊天记录（SQLite）。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.logger import setup_logger
from app.db.book_store import _connect, _lock

logger = setup_logger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_session(conn, book_id: str) -> str:
    """在已持有连接（及调用方锁）时确保会话存在，返回 session_id。"""
    row = conn.execute(
        "SELECT id FROM chat_sessions WHERE book_id = ?",
        (book_id,),
    ).fetchone()
    if row:
        return str(row["id"])
    now = _now()
    session_id = uuid.uuid4().hex
    conn.execute(
        """
        INSERT INTO chat_sessions (id, book_id, title, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, book_id, "默认会话", now, now),
    )
    return session_id


def get_or_create_session(book_id: str) -> dict[str, Any]:
    """一书一线程：存在则返回，否则创建默认会话。"""
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM chat_sessions WHERE book_id = ?",
                (book_id,),
            ).fetchone()
            if row:
                return dict(row)
            now = _now()
            session_id = uuid.uuid4().hex
            conn.execute(
                """
                INSERT INTO chat_sessions (id, book_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, book_id, "默认会话", now, now),
            )
            conn.commit()
            return {
                "id": session_id,
                "book_id": book_id,
                "title": "默认会话",
                "created_at": now,
                "updated_at": now,
            }
        finally:
            conn.close()


def list_messages(book_id: str) -> list[dict[str, Any]]:
    """返回该书默认会话的全部消息（按时间升序）。无会话则空列表。"""
    conn = _connect()
    try:
        session = conn.execute(
            "SELECT id FROM chat_sessions WHERE book_id = ?",
            (book_id,),
        ).fetchone()
        if not session:
            return []
        rows = conn.execute(
            """
            SELECT id, role, content, created_at, sources
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY created_at ASC, rowid ASC
            """,
            (session["id"],),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            raw = item.get("sources") or ""
            try:
                parsed = json.loads(raw) if raw else []
            except json.JSONDecodeError:
                parsed = []
            item["sources"] = parsed if isinstance(parsed, list) else []
            out.append(item)
        return out
    finally:
        conn.close()


def append_turn(
    book_id: str,
    question: str,
    answer: str,
    sources: list[dict] | None = None,
) -> None:
    """追加一轮 user + assistant，并刷新会话 updated_at。"""
    q = (question or "").strip()
    a = (answer or "").strip()
    if not q:
        return
    source_json = json.dumps(sources or [], ensure_ascii=False)
    now = _now()
    with _lock:
        conn = _connect()
        try:
            session_id = _ensure_session(conn, book_id)
            conn.execute(
                """
                INSERT INTO chat_messages (id, session_id, role, content, created_at, sources)
                VALUES (?, ?, 'user', ?, ?, '')
                """,
                (uuid.uuid4().hex, session_id, q, now),
            )
            conn.execute(
                """
                INSERT INTO chat_messages (id, session_id, role, content, created_at, sources)
                VALUES (?, ?, 'assistant', ?, ?, ?)
                """,
                (uuid.uuid4().hex, session_id, a or "（没有返回内容）", now, source_json),
            )
            conn.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            conn.commit()
        finally:
            conn.close()
    logger.debug("已落库问答 book=%s", book_id)


def clear_chat(book_id: str) -> None:
    """清空该书会话消息；保留会话行。"""
    with _lock:
        conn = _connect()
        try:
            session = conn.execute(
                "SELECT id FROM chat_sessions WHERE book_id = ?",
                (book_id,),
            ).fetchone()
            if not session:
                return
            conn.execute(
                "DELETE FROM chat_messages WHERE session_id = ?",
                (session["id"],),
            )
            conn.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                (_now(), session["id"]),
            )
            conn.commit()
        finally:
            conn.close()
