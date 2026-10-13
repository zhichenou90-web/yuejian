"""FastAPI 入口：小说 RAG 问答系统。"""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1_router import router as v1_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logger import setup_logger

logger = setup_logger(__name__)

app = FastAPI(
    title="小说 RAG 问答系统",
    description="长篇小说上传、按章切分、混合检索 + Rerank + DeepSeek 问答",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router)
register_exception_handlers(app)


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok", "service": "novel-rag"}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
    )
