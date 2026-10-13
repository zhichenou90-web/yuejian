"""LLM / Embedding 单例：对话 DeepSeek，向量智谱。"""
from functools import lru_cache

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger(__name__)


@lru_cache(maxsize=1)
def get_chat_model() -> BaseChatModel:
    logger.info(
        "初始化对话模型: model=%s, base=%s",
        settings.llm_chat_model,
        settings.llm_api_base,
    )
    return ChatOpenAI(
        model=settings.llm_chat_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_api_base,
        temperature=0.2,
    )


@lru_cache(maxsize=1)
def get_embedding_model() -> Embeddings:
    logger.info(
        "初始化 Embedding: model=%s, base=%s",
        settings.embedding_model,
        settings.embedding_api_base_resolved,
    )
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.embedding_api_key_resolved,
        base_url=settings.embedding_api_base_resolved,
    )
