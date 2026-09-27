"""运行配置（PRD 1.3、2.2、5.3）。

配置**不需要**任何密钥即可启动：``model_api_key`` 缺失只体现为
``model_configured=false``，健康检查仍然可用。

密钥来源（后者优先级更高）：

1. ``<仓库根>/.env`` 或 ``backend/.env``（便于本地开发，**已在 .gitignore 中**）；
2. 环境变量 ``SCENEWEAVE_MODEL_API_KEY``；
3. 代码显式传入（测试与脚本使用）。

密钥只以 :class:`SecretStr` 保存，绝不写入代码、记录或日志（AGENTS.md 第 3 节）；
健康检查只报告**来源**（environment／dotenv／none），不报告内容。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, PrivateAttr, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .contracts import (
    AnalysisCapability,
    APP_NAME,
    APP_VERSION,
    CONTRACT_VERSION,
    DEFAULT_MODEL_NAME,
)
from .ports import (
    MODEL_PROVIDERS,
    PROVIDER_AUTO,
    PROVIDER_DEEPSEEK,
    PROVIDER_LOCAL,
    PROVIDER_MOCK,
    load_analysis_port,
)

#: 仓库根目录与 backend 目录（绝对路径，避免受工作目录影响）。
BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

#: 允许的 .env 位置，按顺序查找（已存在的文件才会被读取）。
ENV_FILE_CANDIDATES: tuple[Path, ...] = (REPO_ROOT / ".env", BACKEND_DIR / ".env")

#: 模型凭证的环境变量名（供来源判定与提示信息使用）。
MODEL_API_KEY_ENV = "SCENEWEAVE_MODEL_API_KEY"

#: 用于区分「未传 _env_file」与「显式传 None」的哨兵。
_ENV_FILE_UNSET = object()

#: 凭证来源取值。
CREDENTIAL_SOURCE_NONE = "none"
CREDENTIAL_SOURCE_ENVIRONMENT = "environment"
CREDENTIAL_SOURCE_DOTENV = "dotenv"

ENV_TEMPLATE_LINES = (
    "# 复制为 .env 后填入真实值；.env 已被 .gitignore 忽略，不要提交。",
    f"{MODEL_API_KEY_ENV}=",
    "SCENEWEAVE_MODEL_NAME=deepseek-flash",
    "# SCENEWEAVE_MODEL_BASE_URL=https://api.deepseek.com",
    "# SCENEWEAVE_MODEL_FORCE_MOCK=false",
    "# SCENEWEAVE_ANALYSIS_ENABLED=false",
    "# SCENEWEAVE_DATABASE_URL=sqlite:///./sceneweave.db",
)


class Settings(BaseSettings):
    """环境变量或 ``.env``，前缀 ``SCENEWEAVE_``，例如 ``SCENEWEAVE_MODEL_API_KEY``。"""

    model_config = SettingsConfigDict(
        env_prefix="SCENEWEAVE_",
        # 读取仓库根与 backend 下的 .env（不存在则忽略）；测试会用 _env_file=None 关闭。
        env_file=ENV_FILE_CANDIDATES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # 允许 model_name／model_api_key／model_base_url 这类字段名。
        protected_namespaces=(),
    )

    #: 本次实例**实际读取**的 .env 路径（私有属性，不参与序列化，不含内容）。
    _env_files_used: tuple[str, ...] = PrivateAttr(default=())

    def __init__(self, **data: object) -> None:
        """记录本次实际读取的 .env，供 ``model_credential_source`` 判定来源。

        pydantic-settings 的优先级是「显式参数 > 环境变量 > .env > 默认值」；
        这里只在初始化后回看**究竟有没有真的加载过 .env 文件**，不读取其内容。
        """

        explicit = data.get("_env_file", _ENV_FILE_UNSET)
        super().__init__(**data)

        if explicit is _ENV_FILE_UNSET:
            loaded = [str(path) for path in ENV_FILE_CANDIDATES if path.is_file()]
        elif explicit is None:
            loaded = []
        else:
            candidates = explicit if isinstance(explicit, (list, tuple)) else [explicit]
            loaded = [str(path) for path in candidates if Path(str(path)).is_file()]
        self._env_files_used = tuple(loaded)

    app_name: str = APP_NAME
    app_version: str = APP_VERSION
    contract_version: str = CONTRACT_VERSION

    # 服务默认仅监听本机，不把无认证服务暴露到公网（PRD 1.3）。
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)

    # 本地单用户部署的 SQLite 文件（PRD 1.3）；支持 sqlite:/// 前缀写法。
    database_url: str = "sqlite:///./sceneweave.db"

    # 运行模型默认 deepseek-flash；与开发执行模型完全分离（PRD 2.2）。
    model_name: str = DEFAULT_MODEL_NAME
    model_base_url: str | None = None
    model_api_key: SecretStr | None = None
    #: 强制使用确定性 Mock（测试与演示），即使配置了凭证也不联网。
    model_force_mock: bool = False

    #: 模型提供方（PRD 第 8 节「可替换模型适配器」）：
    #: ``auto``（有凭证走云服务，否则 Mock）／``mock``／``deepseek``／``local``。
    #: ``local`` 指本机或局域网内的 OpenAI 兼容推理服务（Ollama／LM Studio／vLLM／llama.cpp）。
    model_provider: str = PROVIDER_AUTO
    #: 本地服务是否发送 ``response_format``（部分实现支持不完整，可关闭）。
    local_include_response_format: bool = True

    @field_validator("model_provider")
    @classmethod
    def _validate_provider(cls, value: str) -> str:
        normalized = (value or PROVIDER_AUTO).strip().lower()
        if normalized not in MODEL_PROVIDERS:
            raise ValueError(
                f"model_provider 必须是 {'／'.join(MODEL_PROVIDERS)} 之一，收到 {value!r}"
            )
        return normalized

    # 分析能力默认关闭；关闭时不得要求外部包已安装（PRD 6.2）。
    analysis_enabled: bool = False

    # 本地开发时前端 dev server 的来源，仅用于 CORS。
    cors_allow_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:5173", "http://localhost:5173"]
    )

    @property
    def database_path(self) -> str:
        """SQLite 文件路径。``sqlite:///`` 前缀会被去掉，便于测试注入临时文件。"""

        prefix = "sqlite:///"
        if self.database_url.startswith(prefix):
            return self.database_url[len(prefix) :]
        return self.database_url

    @property
    def model_api_key_present(self) -> bool:
        """是否提供了非空凭证。只返回布尔值，不泄露密钥内容。"""

        if self.model_api_key is None:
            return False
        return bool(self.model_api_key.get_secret_value().strip())

    @property
    def resolved_provider(self) -> str:
        """实际生效的提供方（``auto`` 在这里被解析为具体实现）。

        - ``model_force_mock`` → ``mock``（即使配了密钥也不联网）
        - ``auto`` → 有凭证 ``deepseek``，否则 ``mock``
        - 其余原样返回
        """

        if self.model_force_mock:
            return PROVIDER_MOCK
        if self.model_provider == PROVIDER_AUTO:
            return PROVIDER_DEEPSEEK if self.model_api_key_present else PROVIDER_MOCK
        return self.model_provider

    @property
    def model_configured(self) -> bool:
        """是否会使用**真实**模型（而非确定性 Mock）。

        - ``mock`` → ``False``
        - ``local`` → ``True``（本地服务不需要凭证）
        - ``deepseek`` → 取决于是否提供了凭证

        只返回布尔值，不泄露密钥内容。
        """

        provider = self.resolved_provider
        if provider == PROVIDER_MOCK:
            return False
        if provider == PROVIDER_LOCAL:
            return True
        return self.model_api_key_present

    @property
    def model_endpoint(self) -> str:
        """实际会请求的 Chat Completions 地址（不含凭证），便于排错。"""

        if self.resolved_provider == PROVIDER_LOCAL:
            from .ports import DEFAULT_LOCAL_BASE_URL

            base = (self.model_base_url or DEFAULT_LOCAL_BASE_URL).rstrip("/")
            return f"{base}/chat/completions"
        if self.resolved_provider == PROVIDER_DEEPSEEK:
            from .ports import DeepSeekModelClient  # noqa: F401  仅为语义清晰

            from .ports.deepseek import DEFAULT_BASE_URL

            base = (self.model_base_url or DEFAULT_BASE_URL).rstrip("/")
            return f"{base}/chat/completions"
        return ""

    @property
    def model_credential_source(self) -> str:
        """凭证来源（**不含**凭证内容）：``environment``／``dotenv``／``none``。

        用途：让操作者确认「.env 是否被真正读取」，而不必暴露密钥。
        """

        # 注意：这里判断的是「有没有凭证」，而不是「是否使用真实模型」——
        # 本地提供方不需要凭证，其来源必须如实报告为 none。
        if not self.model_api_key_present:
            return CREDENTIAL_SOURCE_NONE
        # 环境变量优先于 .env（与 pydantic-settings 的优先级一致）。
        if os.environ.get(MODEL_API_KEY_ENV, "").strip():
            return CREDENTIAL_SOURCE_ENVIRONMENT
        if self._env_files_used:
            return CREDENTIAL_SOURCE_DOTENV
        return CREDENTIAL_SOURCE_ENVIRONMENT

    @property
    def env_files_present(self) -> tuple[str, ...]:
        """本次实例实际读取的 .env 路径；只返回路径，不返回内容。"""

        return self._env_files_used

    @property
    def analysis_capability(self) -> AnalysisCapability:
        """分析能力摘要。M00 恒为未安装外部包。"""

        port = self.analysis_port
        enabled = getattr(port, "enabled", False)
        capability = getattr(port, "capability", None)
        return AnalysisCapability(
            enabled=enabled,
            external_package_installed=(
                capability.external_package_installed if capability is not None else enabled
            ),
            reason=capability.reason if capability is not None else None,
        )

    @property
    def analysis_port(self):
        """按配置返回分析端口。M00 恒为 Disabled，不会导入外部包。"""

        return load_analysis_port(
            enabled=self.analysis_enabled,
            provider=self.resolved_provider,
            api_key=self.model_api_key.get_secret_value() if self.model_api_key_present else None,
            base_url=self.model_base_url,
            model=self.model_name,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """进程级配置单例。测试可直接构造 ``Settings`` 覆盖。"""

    return Settings()


__all__ = ["Settings", "get_settings"]
