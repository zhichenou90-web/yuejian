"""全局异常处理。"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logger import setup_logger

logger = setup_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理异常 path=%s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={"code": 500, "message": f"服务器错误: {exc}"},
        )
