"""FastAPI 应用入口。

- M00：健康检查、契约自检、契约模型 OpenAPI 注入。
- M01：角色模板与场景配置接口；数据库在 lifespan 中初始化并执行迁移。

``create_app()`` 本身**不触碰数据库**，因此导出 OpenAPI 不会创建任何文件。
运行控制、事件与 SSE 属于 M04；行为分析属于 M06。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .analysis import AnalysisService
from .api import (
    analysis_router,
    m00_router,
    runtime_router,
    scenes_router,
    templates_router,
)
from .api.errors import register_error_handlers
from .config import Settings, get_settings
from .contracts import APP_NAME, APP_VERSION, ModelParams, contract_json_schemas
from .domain import SceneService, TemplateService
from .ports import build_model_port
from .runtime import Broadcaster, SceneRunner
from .storage import (
    AnalysisRepository,
    Database,
    RuntimeRepository,
    SceneRepository,
    TemplateRepository,
)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """初始化存储、领域服务与运行器。

    - M01：schema 迁移与模板／场景服务。**不**在启动时自动写入预置模板，
      以免用户移除模板后又被悄悄恢复；预置模板由 ``POST /api/scenes/preset``
      按需补齐（tasks/M01.md §3.4）。
    - M04：装配运行器，并执行**重启恢复**——把残留的在途请求标记 `UNKNOWN`
      并把所属场景暂停（原因 `PROCESS_INTERRUPT`），**不自动恢复付费请求**。
    - 未配置模型凭证时使用确定性 Mock，绝不发起网络调用。
    """

    settings: Settings = app.state.settings
    database = Database(settings.database_path)
    applied = database.migrate()

    template_service = TemplateService(TemplateRepository(database))
    scene_repository = SceneRepository(database)
    scene_service = SceneService(scene_repository, template_service)
    runtime_repository = RuntimeRepository(database)

    # 允许调用方注入端口（测试、演示与 M07 的真实冒烟），默认按配置装配。
    model_port = app.state.injected_model_port or build_model_port(
        api_key=settings.model_api_key.get_secret_value() if settings.model_api_key else None,
        base_url=settings.model_base_url,
        force_mock=settings.model_force_mock,
        provider=settings.model_provider,
        include_response_format=settings.local_include_response_format,
    )
    runner = SceneRunner(
        database=database,
        scenes=scene_repository,
        runtime=runtime_repository,
        model_port=model_port,
        # 运行参数来自配置：SCENEWEAVE_MODEL_NAME 等设置因此真正生效。
        model_params=ModelParams(model=settings.model_name),
    )
    recovered = runner.recover_after_restart()

    analysis_service = AnalysisService(
        scenes=scene_repository,
        runtime=runtime_repository,
        repository=AnalysisRepository(database),
        port_factory=lambda: app.state.injected_analysis_port
        or app.state.settings.analysis_port,
        snapshot_provider=runner.snapshot,
    )

    app.state.database = database
    app.state.applied_migrations = applied
    app.state.template_service = template_service
    app.state.scene_service = scene_service
    app.state.runtime_repository = runtime_repository
    app.state.model_port = model_port
    app.state.scene_runner = runner
    app.state.analysis_service = analysis_service
    app.state.recovered_scenes = recovered
    try:
        yield
    finally:
        await runner.shutdown()


def create_app(
    settings: Settings | None = None,
    *,
    model_port=None,
    analysis_port=None,
) -> FastAPI:
    """创建应用。

    ``settings`` 为空时读取环境配置（不需要任何密钥）；``model_port``／``analysis_port``
    可注入自定义端口（测试用脚本化 Mock 或假分析器），默认按配置装配。
    """

    resolved = settings or get_settings()

    app = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        description=(
            "SceneWeave（角色互动沙盒）后端。M00 提供工程基础与公共契约；"
            "M01 提供角色模板与场景配置；M02/M03 提供可见性、调度与模型适配；"
            "M04 提供运行控制、事件、时间线、角色视角与 SSE；M06 提供只读行为分析。"
        ),
        lifespan=_lifespan,
    )
    app.state.settings = resolved
    app.state.injected_model_port = model_port
    app.state.injected_analysis_port = analysis_port

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_allow_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    register_error_handlers(app)

    app.include_router(m00_router)
    app.include_router(templates_router)
    app.include_router(scenes_router)
    app.include_router(runtime_router)
    app.include_router(analysis_router)

    # M02～M06 的路由尚未建立时，行动／事件／端口等模型不会被任何路由引用，
    # 也就不会出现在 OpenAPI 组件里。这里把登记过的契约模型 schema 合并进去，
    # 使前端可以一次性生成**完整**契约类型（PRD 第 8 节）。
    default_openapi = app.openapi

    def _openapi_with_contract_models():  # type: ignore[no-untyped-def]
        if app.openapi_schema is not None:
            return app.openapi_schema
        spec = default_openapi()
        components = spec.setdefault("components", {}).setdefault("schemas", {})
        for name, schema in contract_json_schemas().items():
            # 路由已生成的同名 schema 优先，避免覆盖 FastAPI 的既有定义。
            components.setdefault(name, schema)
        app.openapi_schema = spec
        return spec

    app.openapi = _openapi_with_contract_models  # type: ignore[method-assign]
    return app


app = create_app()

__all__ = ["app", "create_app"]
