"""外部端口包：首版只有模型行动与行为分析两个端口（PRD 第 8 节）。

不建设通用插件系统；新增端口必须先改契约与架构文档。
"""

from __future__ import annotations

from .action_parser import (
    ALLOWED_FIELDS,
    FINISH_REASON_DETAILS,
    FINISH_REASON_FAILURES,
    NORMAL_FINISH_REASONS,
    parse_action_content,
    validate_references,
)
from .analysis import (
    DISCLAIMER,
    AnalysisPort,
    DisabledAnalysisPort,
    MockAnalysisPort,
    load_analysis_port,
)
from .deepseek import DeepSeekModelClient
from .local import (
    DEFAULT_LOCAL_BASE_URL,
    DEFAULT_LOCAL_MODEL_NAME,
    LLAMA_CPP_BASE_URL,
    LM_STUDIO_BASE_URL,
    OLLAMA_BASE_URL,
    VLLM_BASE_URL,
    LocalModelClient,
)
from .model import (
    MODEL_PROVIDERS,
    PROVIDER_AUTO,
    PROVIDER_DEEPSEEK,
    PROVIDER_LOCAL,
    PROVIDER_MOCK,
    MockModelPort,
    ModelPort,
    build_model_port,
)

__all__ = [
    "DEFAULT_LOCAL_BASE_URL",
    "DEFAULT_LOCAL_MODEL_NAME",
    "LLAMA_CPP_BASE_URL",
    "LM_STUDIO_BASE_URL",
    "MODEL_PROVIDERS",
    "OLLAMA_BASE_URL",
    "PROVIDER_AUTO",
    "PROVIDER_DEEPSEEK",
    "PROVIDER_LOCAL",
    "PROVIDER_MOCK",
    "VLLM_BASE_URL",
    "LocalModelClient",
    "ALLOWED_FIELDS",
    "AnalysisPort",
    "DeepSeekModelClient",
    "DisabledAnalysisPort",
    "MockAnalysisPort",
    "DISCLAIMER",
    "FINISH_REASON_DETAILS",
    "FINISH_REASON_FAILURES",
    "NORMAL_FINISH_REASONS",
    "MockModelPort",
    "ModelPort",
    "build_model_port",
    "load_analysis_port",
    "parse_action_content",
    "validate_references",
]
