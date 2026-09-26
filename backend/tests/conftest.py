"""共享测试夹具。

全部测试**不需要任何模型密钥**，也不访问网络：默认使用 Mock 端口与临时
SQLite 文件，并且用 ``Settings(...)`` 显式覆盖环境变量，避免开发机上已有的
``SCENEWEAVE_*`` 变量影响结果。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from role_theater.config import Settings
from role_theater.domain import SceneService, TemplateService
from role_theater.main import create_app
from role_theater.storage import Database, SceneRepository, TemplateRepository


@pytest.fixture
def keyless_settings() -> Settings:
    """无密钥配置：不应阻止启动与健康检查。"""

    return Settings(
        # _env_file=None：测试永不读取真实 .env（否则会带着真实密钥发起联网调用）。
        _env_file=None,
        model_api_key=None,
        model_base_url=None,
        analysis_enabled=False,
    )


@pytest.fixture
def keyless_client(keyless_settings: Settings) -> TestClient:
    return TestClient(create_app(keyless_settings))


@pytest.fixture
def configured_client() -> TestClient:
    """带占位凭证（非真实密钥）的配置，用于验证凭证不外泄。"""

    return TestClient(
        create_app(
            Settings(
                _env_file=None,
                model_api_key="placeholder-not-a-real-key",
                analysis_enabled=True,
            )
        )
    )


# --- M01：临时数据库与领域服务 ------------------------------------------------


@pytest.fixture
def m01_settings(tmp_path: Path) -> Settings:
    """每个测试一个临时 SQLite 文件，互不干扰。"""

    return Settings(
        _env_file=None,
        model_api_key=None,
        model_base_url=None,
        analysis_enabled=False,
        database_url=f"sqlite:///{tmp_path / 'sceneweave-test.db'}",
    )


@pytest.fixture
def api_client(m01_settings: Settings) -> Iterator[TestClient]:
    """启动 lifespan（执行迁移）的测试客户端。"""

    with TestClient(create_app(m01_settings)) as client:
        yield client


@pytest.fixture
def database(tmp_path: Path) -> Database:
    """已迁移完成的临时数据库。"""

    db = Database(tmp_path / "sceneweave-unit.db")
    db.migrate()
    return db


@pytest.fixture
def make_client(tmp_path: Path) -> Callable[..., Iterator[TestClient]]:
    """按脚本创建带确定性 Mock 模型端口的测试客户端（上下文管理器工厂）。

    用法::

        with make_client(script=[ActionDraft(action=ActionType.SPEAK, text="你好。")]) as client:
            ...

    未提供脚本时 Mock 默认返回 PASS，因此不会伪造发言。
    """

    from contextlib import contextmanager

    from role_theater.ports import MockModelPort

    counter = {"n": 0}

    @contextmanager
    def _make(
        script=None,
        *,
        default_draft=None,
        model_port=None,
        injected_analysis_port=None,
        **settings_kwargs,
    ):
        counter["n"] += 1
        resolved = {
            "_env_file": None,
            "model_api_key": None,
            "analysis_enabled": False,
            "database_url": f"sqlite:///{tmp_path / ('client-' + str(counter['n']) + '.db')}",
        }
        resolved.update(settings_kwargs)
        settings = Settings(**resolved)
        port = model_port or MockModelPort(script=list(script or []), default_draft=default_draft)
        with TestClient(
            create_app(settings, model_port=port, analysis_port=injected_analysis_port)
        ) as client:
            yield client

    return _make


class DeterministicIds:
    """可预测的 ID 生成器，便于断言（测试专用）。"""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def factory(self, prefix: str) -> Callable[[], str]:
        def _next() -> str:
            self._counters[prefix] = self._counters.get(prefix, 0) + 1
            return f"{prefix}-{self._counters[prefix]}"

        return _next


@pytest.fixture
def fixed_clock() -> Callable[[], datetime]:
    """固定时间戳：让 created_at／updated_at 的断言可确定。"""

    moment = datetime(2026, 9, 26, 20, 0, tzinfo=UTC)
    return lambda: moment


@pytest.fixture
def services(
    database: Database,
    fixed_clock: Callable[[], datetime],
) -> tuple[TemplateService, SceneService]:
    """确定性的领域服务（固定时钟与递增 ID）。"""

    ids = DeterministicIds()
    template_service = TemplateService(
        TemplateRepository(database),
        clock=fixed_clock,
        id_factory=ids.factory("tpl"),
    )
    scene_service = SceneService(
        SceneRepository(database),
        template_service,
        clock=fixed_clock,
        scene_id_factory=ids.factory("scn"),
        agent_id_factory=ids.factory("agt"),
    )
    return template_service, scene_service
