"""章内切片。"""
from __future__ import annotations

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.core.logger import setup_logger
from app.services.novel_parser import Chapter

logger = setup_logger(__name__)


def _splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=[
            "\n\n",
            "\n",
            "。”",
            "！”",
            "？”",
            "。",
            "！",
            "？",
            "；",
            " ",
            "",
        ],
    )


def chapters_to_documents(
    book_id: str,
    book_title: str,
    chapters: list[Chapter],
) -> list[Document]:
    """将章节切为带元数据的 Document 列表。"""
    splitter = _splitter()
    docs: list[Document] = []
    for ch in chapters:
        # 把章节标题拼进正文，提升检索时对「第X章」类问题的命中
        text = f"{ch.chapter_title}\n\n{ch.content}"
        parts = splitter.split_text(text)
        for i, part in enumerate(parts):
            docs.append(
                Document(
                    page_content=part,
                    metadata={
                        "book_id": book_id,
                        "book_title": book_title,
                        "chapter_index": ch.chapter_index,
                        "chapter_no": ch.chapter_no if ch.chapter_no is not None else -1,
                        "chapter_title": ch.chapter_title,
                        "chunk_in_chapter": i,
                    },
                )
            )
    logger.info(
        "切片完成: book=%s, chapters=%d, chunks=%d",
        book_title,
        len(chapters),
        len(docs),
    )
    return docs
