"""外部依赖注入：从 ``app.state`` 取领域服务。

服务在 FastAPI 的 lifespan 中创建（届时才触碰数据库文件），因此
``create_app()`` 本身没有文件系统副作用——OpenAPI 导出不会创建数据库。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from ..analysis import AnalysisService
from ..domain import SceneService, TemplateService
from ..runtime import SceneRunner


def _service(request: Request, name: str):
    service = getattr(request.app.state, name, None)
    if service is None:
        raise RuntimeError(
            "应用未初始化：请通过 FastAPI lifespan 启动应用"
            "（TestClient 需使用上下文管理器，或改用 create_app + lifespan）"
        )
    return service


def get_template_service(request: Request) -> TemplateService:
    return _service(request, "template_service")


def get_scene_service(request: Request) -> SceneService:
    return _service(request, "scene_service")


def get_runner(request: Request) -> SceneRunner:
    return _service(request, "scene_runner")


def get_analysis_service(request: Request) -> AnalysisService:
    return _service(request, "analysis_service")


TemplateServiceDep = Annotated[TemplateService, Depends(get_template_service)]
SceneServiceDep = Annotated[SceneService, Depends(get_scene_service)]
RunnerDep = Annotated[SceneRunner, Depends(get_runner)]
AnalysisServiceDep = Annotated[AnalysisService, Depends(get_analysis_service)]
