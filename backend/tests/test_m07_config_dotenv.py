"""配置与凭证来源（PRD 1.3、2.2；`docs/RELEASE.md` §6）。

这些测试**绝不读取真实 .env**：需要验证 dotenv 行为时显式传入临时文件路径，
避免开发机上已有的真实密钥被测试吞掉并触发联网调用。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from role_theater.config import (
    CREDENTIAL_SOURCE_DOTENV,
    CREDENTIAL_SOURCE_ENVIRONMENT,
    CREDENTIAL_SOURCE_NONE,
    MODEL_API_KEY_ENV,
    Settings,
)
from role_theater.main import create_app

PLACEHOLDER = "placeholder-dotenv-value"


def _write_env(path: Path, **values: str) -> Path:
    lines = [f"{key}={value}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_no_credentials_means_not_configured(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, model_api_key=None)

    assert settings.model_configured is False
    assert settings.model_credential_source == CREDENTIAL_SOURCE_NONE


def test_dotenv_file_is_loaded_and_reported(tmp_path: Path) -> None:
    env_file = _write_env(
        tmp_path / ".env",
        **{MODEL_API_KEY_ENV: PLACEHOLDER, "SCENEWEAVE_MODEL_NAME": "deepseek-v4-pro"},
    )

    settings = Settings(_env_file=env_file)

    assert settings.model_configured is True
    assert settings.model_name == "deepseek-v4-pro"
    assert settings.model_credential_source == CREDENTIAL_SOURCE_DOTENV


def test_environment_variable_wins_over_dotenv(tmp_path: Path, monkeypatch) -> None:
    env_file = _write_env(tmp_path / ".env", **{MODEL_API_KEY_ENV: "from-dotenv"})
    monkeypatch.setenv(MODEL_API_KEY_ENV, "from-environment")

    settings = Settings(_env_file=env_file)

    assert settings.model_credential_source == CREDENTIAL_SOURCE_ENVIRONMENT
    assert settings.model_api_key is not None
    assert settings.model_api_key.get_secret_value() == "from-environment"


def test_explicit_argument_wins_over_everything(tmp_path: Path, monkeypatch) -> None:
    env_file = _write_env(tmp_path / ".env", **{MODEL_API_KEY_ENV: "from-dotenv"})
    monkeypatch.setenv(MODEL_API_KEY_ENV, "from-environment")

    settings = Settings(_env_file=env_file, model_api_key="from-code")

    assert settings.model_api_key is not None
    assert settings.model_api_key.get_secret_value() == "from-code"


def test_credential_never_appears_in_repr_or_dump(tmp_path: Path) -> None:
    env_file = _write_env(tmp_path / ".env", **{MODEL_API_KEY_ENV: PLACEHOLDER})

    settings = Settings(_env_file=env_file)

    assert PLACEHOLDER not in repr(settings)
    assert PLACEHOLDER not in str(settings.model_dump())
    assert PLACEHOLDER not in str(settings.model_dump_json())


def test_health_reports_source_without_leaking_the_credential(tmp_path: Path) -> None:
    env_file = _write_env(tmp_path / ".env", **{MODEL_API_KEY_ENV: PLACEHOLDER})
    settings = Settings(_env_file=env_file, database_url=f"sqlite:///{tmp_path/'health.db'}")

    with TestClient(create_app(settings)) as client:
        body = client.get("/api/health").json()
        raw = client.get("/api/health").text

    assert body["model_configured"] is True
    assert body["model_credential_source"] == CREDENTIAL_SOURCE_DOTENV
    assert PLACEHOLDER not in raw


def test_env_example_template_has_names_but_no_values() -> None:
    """模板可以入库，因为它只有变量名与空值；真实 .env 由 .gitignore 忽略。"""

    repo_root = Path(__file__).resolve().parents[2]
    template = (repo_root / ".env.example").read_text(encoding="utf-8")

    assert MODEL_API_KEY_ENV in template
    for line in template.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() == MODEL_API_KEY_ENV:
            assert value == "", "模板中的密钥必须为空"


def test_gitignore_ignores_env_but_keeps_the_template() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    rules = (repo_root / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in rules
    assert ".env.*" in rules
    assert "!.env.example" in rules, "模板必须被显式保留，否则新人无法知道变量名"


def test_default_env_file_candidates_are_repository_paths() -> None:
    from role_theater.config import BACKEND_DIR, ENV_FILE_CANDIDATES, REPO_ROOT

    assert ENV_FILE_CANDIDATES == (REPO_ROOT / ".env", BACKEND_DIR / ".env")
    assert REPO_ROOT.name == "SceneWeave"
    assert BACKEND_DIR.name == "backend"


@pytest.mark.parametrize("force_mock", [True, False])
def test_force_mock_does_not_depend_on_credentials(tmp_path: Path, force_mock: bool) -> None:
    env_file = _write_env(tmp_path / ".env", **{MODEL_API_KEY_ENV: PLACEHOLDER})

    settings = Settings(_env_file=env_file, model_force_mock=force_mock)

    assert settings.model_force_mock is force_mock
    # 凭证来源与是否强制 Mock 无关。
    assert settings.model_credential_source == CREDENTIAL_SOURCE_DOTENV


def test_local_env_file_is_expected_and_must_stay_ignored() -> None:
    """本地 `.env` 是**预期存在**的（操作者自行填入密钥），因此这里只断言它被忽略。

    注意：本条**不得**断言 `.env` 不存在——否则操作者按文档创建 `.env` 后测试会失败。
    真正的保障是 `.gitignore` 规则 + 模板只含变量名（由上面的用例覆盖）。
    """

    repo_root = Path(__file__).resolve().parents[2]
    rules = [line.strip() for line in (repo_root / ".gitignore").read_text(encoding="utf-8").splitlines()]

    assert ".env" in rules, "本地 .env 必须被忽略"
    assert "!.env.example" in rules, "模板必须保留"
    # 若操作者已创建 .env，它也不得包含任何被提交的痕迹：这里只检查它是普通文件。
    for candidate in (repo_root / ".env", repo_root / "backend" / ".env"):
        if candidate.exists():
            assert candidate.is_file()


def test_environment_probe_reports_presence_only(monkeypatch) -> None:
    """来源判定只看环境变量是否存在，不读取内容。"""

    monkeypatch.setenv(MODEL_API_KEY_ENV, "x")
    settings = Settings(_env_file=None, model_api_key="y")

    assert settings.model_credential_source == CREDENTIAL_SOURCE_ENVIRONMENT
    assert os.environ[MODEL_API_KEY_ENV] == "x"
