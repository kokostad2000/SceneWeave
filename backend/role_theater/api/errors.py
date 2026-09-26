"""领域错误与契约校验错误 → HTTP 响应的统一映射。

统一使用 M00 的 ``ApiError`` 契约，使错误响应体在所有模块中一致
（``request_id`` 字段留给 M04 的幂等命令使用）。
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..contracts import ApiError
from ..domain import DomainError

#: 契约层字段校验失败：入站参数非法，不新增模型请求（PRD 5.3）。
CONTRACT_VALIDATION_ERROR = "validation_error"


def _payload(error: str, detail: str, *, retryable: bool = False) -> dict:
    return ApiError(error=error, detail=detail, retryable=retryable).model_dump(mode="json")


def register_error_handlers(app: FastAPI) -> None:
    """注册三类错误处理器。"""

    @app.exception_handler(RequestValidationError)
    async def _request_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_payload(CONTRACT_VALIDATION_ERROR, str(exc.errors())),
        )

    @app.exception_handler(ValidationError)
    async def _domain_validation_handler(_: Request, exc: ValidationError) -> JSONResponse:
        """领域层用 Pydantic 复校时抛出的错误，同属入站参数问题。"""

        return JSONResponse(
            status_code=422,
            content=_payload(CONTRACT_VALIDATION_ERROR, str(exc)),
        )

    @app.exception_handler(DomainError)
    async def _domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=_payload(exc.code, str(exc)),
        )
