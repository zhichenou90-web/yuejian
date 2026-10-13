"""全局配置：DeepSeek 对话 + 智谱 Embedding/Rerank。"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """从 .env 加载的全局配置。"""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # DeepSeek 对话
    llm_api_key: str = ""
    llm_api_base: str = "https://api.deepseek.com/v1"
    llm_chat_model: str = "deepseek-flash"

    # 智谱 Embedding
    embedding_api_key: str = ""
    embedding_api_base: str = "https://open.bigmodel.cn/api/paas/v4"
    embedding_model: str = "embedding-3"

    app_host: str = "0.0.0.0"
    app_port: int = 8000

    data_dir: str = "./data"
    books_dir: str = "./data/books"
    chroma_dir: str = "./chroma_db"
    sqlite_path: str = "./data/novel_rag.db"

    chunk_size: int = 1200
    chunk_overlap: int = 180
    min_chapter_chars: int = 200

    # 最终送入 LLM 的片段数；过多会引入后期噪声，宜与「最多 3 条依据」对齐
    retrieval_top_k: int = 3
    retrieval_score_threshold: float = 0.22
    hybrid_search_enabled: bool = True
    hybrid_recall_top_k: int = 20
    rerank_enabled: bool = True
    rerank_recall_top_k: int = 20
    rerank_top_n: int = 8

    log_level: str = "INFO"

    @property
    def embedding_api_key_resolved(self) -> str:
        return self.embedding_api_key or self.llm_api_key

    @property
    def embedding_api_base_resolved(self) -> str:
        return self.embedding_api_base or self.llm_api_base

    @staticmethod
    def _resolve(path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = BASE_DIR / p
        return p

    @property
    def data_dir_path(self) -> Path:
        p = self._resolve(self.data_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def books_dir_path(self) -> Path:
        p = self._resolve(self.books_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def chroma_dir_path(self) -> Path:
        return self._resolve(self.chroma_dir)

    @property
    def sqlite_path_path(self) -> Path:
        p = self._resolve(self.sqlite_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
