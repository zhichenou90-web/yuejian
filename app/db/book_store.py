"""书籍与章节元数据（SQLite）。"""
from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger(__name__)
_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(settings.sqlite_path_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with _lock:
        conn = _connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS books (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    chapter_count INTEGER NOT NULL DEFAULT 0,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    split_mode TEXT NOT NULL DEFAULT 'chapter',
                    warning TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    last_chapter_index INTEGER NOT NULL DEFAULT 0,
                    last_read_at TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS chapters (
                    book_id TEXT NOT NULL,
                    chapter_index INTEGER NOT NULL,
                    chapter_no INTEGER,
                    chapter_title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    PRIMARY KEY (book_id, chapter_index),
                    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    book_id TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL DEFAULT '默认会话',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session
                    ON chat_messages(session_id, created_at);
                """
            )
            _migrate_books_columns(conn)
            _migrate_chat_columns(conn)
            conn.commit()
        finally:
            conn.close()


def _migrate_chat_columns(conn: sqlite3.Connection) -> None:
    """助手消息可附带出处 JSON，旧库补列。"""
    cols = {
        str(r[1]) for r in conn.execute("PRAGMA table_info(chat_messages)").fetchall()
    }
    if "sources" not in cols:
        conn.execute(
            "ALTER TABLE chat_messages ADD COLUMN sources TEXT NOT NULL DEFAULT ''"
        )


def _migrate_books_columns(conn: sqlite3.Connection) -> None:
    """为已有库补齐阅读进度字段。"""
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(books)").fetchall()}
    if "last_chapter_index" not in cols:
        conn.execute(
            "ALTER TABLE books ADD COLUMN last_chapter_index INTEGER NOT NULL DEFAULT 0"
        )
    if "last_read_at" not in cols:
        conn.execute(
            "ALTER TABLE books ADD COLUMN last_read_at TEXT NOT NULL DEFAULT ''"
        )


def create_book(
    title: str,
    filename: str,
    chapters: list[dict[str, Any]],
    chunk_count: int,
    split_mode: str,
    warning: str = "",
    book_id: str | None = None,
) -> str:
    book_id = book_id or uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO books
                (id, title, filename, chapter_count, chunk_count, split_mode, warning, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    book_id,
                    title,
                    filename,
                    len(chapters),
                    chunk_count,
                    split_mode,
                    warning,
                    now,
                ),
            )
            conn.executemany(
                """
                INSERT INTO chapters
                (book_id, chapter_index, chapter_no, chapter_title, content)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        book_id,
                        c["chapter_index"],
                        c.get("chapter_no"),
                        c["chapter_title"],
                        c["content"],
                    )
                    for c in chapters
                ],
            )
            conn.commit()
        finally:
            conn.close()
    logger.info("已写入书籍 %s (%s), 章=%d", title, book_id, len(chapters))
    return book_id


def list_books() -> list[dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT * FROM books
            ORDER BY
                CASE WHEN last_read_at IS NULL OR last_read_at = '' THEN 0 ELSE 1 END DESC,
                last_read_at DESC,
                created_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_book(book_id: str) -> dict[str, Any] | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM books WHERE id = ?", (book_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_chapters(book_id: str) -> list[dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT book_id, chapter_index, chapter_no, chapter_title,
                   length(content) AS content_length
            FROM chapters
            WHERE book_id = ?
            ORDER BY chapter_index
            """,
            (book_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_chapter(book_id: str, chapter_index: int) -> dict[str, Any] | None:
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT * FROM chapters
            WHERE book_id = ? AND chapter_index = ?
            """,
            (book_id, chapter_index),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_reading_progress(book_id: str, chapter_index: int) -> bool:
    """记录该书最近阅读章节，供换书/刷新恢复。"""
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute(
                """
                UPDATE books
                SET last_chapter_index = ?, last_read_at = ?
                WHERE id = ?
                """,
                (int(chapter_index), now, book_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def delete_book(book_id: str) -> bool:
    with _lock:
        conn = _connect()
        try:
            # chat_sessions / chat_messages 经 FK CASCADE 随 books 删除
            conn.execute("DELETE FROM chapters WHERE book_id = ?", (book_id,))
            cur2 = conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
            conn.commit()
            return cur2.rowcount > 0
        finally:
            conn.close()


# 启动时初始化
init_db()
