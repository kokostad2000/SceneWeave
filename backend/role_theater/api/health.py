"""健康检查与契约自检路由（M00）。

健康检查**不需要任何密钥**，也不发起任何外部调用；未配置模型凭证时只把
``model_configured`` 置为 false，仍返回 200。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..config import Settings
from ..contracts import ContractSummary, HealthResponse, RunState, build_contract_summary

router = APIRouter(prefix="/api", tags=["m00"])


def _settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        return Settings()
    return settings


@router.get("/health", response_model=HealthResponse, summary="最小健康检查")
async def health(request: Request) -> HealthResponse:
    settings = _settings(request)
    capability = settings.analysis_capability
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        app_version=settings.app_version,
        contract_version=settings.contract_version,
        # M00 没有会话运行时，健康检查固定报告初始状态。
        run_state=RunState.READY,
        analysis_enabled=capability.enabled,
        model_configured=settings.model_configured,
        model_credential_source=settings.model_credential_source,
        model_provider=settings.resolved_provider,
    )


@router.get(
    "/contracts/summary",
    response_model=ContractSummary,
    summary="契约自检摘要（枚举、长度上限、预算、运行参数、端口）",
)
async def contracts_summary() -> ContractSummary:
    return build_contract_summary()
