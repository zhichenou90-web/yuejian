"""书籍相关 Schema。"""
from pydantic import BaseModel, Field


class BookInfo(BaseModel):
    id: str
    title: str
    filename: str
    chapter_count: int
    chunk_count: int
    split_mode: str = "chapter"
    warning: str = ""
    created_at: str = ""
    last_chapter_index: int = 0
    last_read_at: str = ""


class ChapterBrief(BaseModel):
    book_id: str
    chapter_index: int
    chapter_no: int | None = None
    chapter_title: str
    content_length: int = 0


class ChapterDetail(BaseModel):
    book_id: str
    chapter_index: int
    chapter_no: int | None = None
    chapter_title: str
    content: str


class IngestResult(BaseModel):
    book_id: str
    title: str
    chapter_count: int
    chunk_count: int
    split_mode: str
    warning: str = ""
