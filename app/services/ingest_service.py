"""小说入库编排。"""
from __future__ import annotations

import uuid
from pathlib import Path

from app.core.config import settings
from app.core.logger import setup_logger
from app.db import book_store, keyword_store, vector_store
from app.services.chunker import chapters_to_documents
from app.services.novel_parser import parse_novel_bytes

logger = setup_logger(__name__)


def ingest_novel_file(file_path: Path, filename: str | None = None) -> dict:
    raw = file_path.read_bytes()
    return ingest_novel_bytes(raw, filename or file_path.name)


def ingest_novel_bytes(raw: bytes, filename: str) -> dict:
    """解析 → 切分 → SQLite → 向量化 → BM25。"""
    parsed = parse_novel_bytes(raw, filename=filename)
    book_id = uuid.uuid4().hex
    docs = chapters_to_documents(book_id, parsed.title, parsed.chapters)

    book_dir = settings.books_dir_path / book_id
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "original.txt").write_bytes(raw)

    chapter_dicts = [
        {
            "chapter_index": c.chapter_index,
            "chapter_no": c.chapter_no,
            "chapter_title": c.chapter_title,
            "content": c.content,
        }
        for c in parsed.chapters
    ]
    book_store.create_book(
        title=parsed.title,
        filename=filename,
        chapters=chapter_dicts,
        chunk_count=len(docs),
        split_mode=parsed.split_mode,
        warning=parsed.warning,
        book_id=book_id,
    )

    vector_store.add_documents(docs)
    keyword_store.rebuild_for_book(book_id)

    result = {
        "book_id": book_id,
        "title": parsed.title,
        "chapter_count": len(parsed.chapters),
        "chunk_count": len(docs),
        "split_mode": parsed.split_mode,
        "warning": parsed.warning,
    }
    logger.info("入库完成: %s", result)
    return result


def remove_book(book_id: str) -> bool:
    vector_store.delete_by_book(book_id)
    keyword_store.drop_book_index(book_id)
    book_dir = settings.books_dir_path / book_id
    if book_dir.exists():
        for f in book_dir.iterdir():
            f.unlink()
        book_dir.rmdir()
    return book_store.delete_book(book_id)
