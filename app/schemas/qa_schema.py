"""问答 Schema。"""
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(..., description="user / assistant")
    content: str


class SourceRef(BaseModel):
    """答案依据的章节，供前端跳转。"""

    chapter_index: int
    chapter_title: str
    excerpt: str = ""


class ChatRequest(BaseModel):
    book_id: str
    question: str = Field(..., min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)
    # 当前打开的章节。仅「这一章 / 刚才」类问题会用来限定检索；全局剧透与回顾忽略它。
    chapter_index: int | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceRef] = Field(default_factory=list)


class StoredChatMessage(BaseModel):
    id: str
    role: str
    content: str
    created_at: str
    sources: list[SourceRef] = Field(default_factory=list)


class BookChatResponse(BaseModel):
    session_id: str | None = None
    messages: list[StoredChatMessage] = Field(default_factory=list)
