"""M06 行为分析：边界规则、受控客户端、外部适配与只读分析服务。"""

from __future__ import annotations

from .boundary import BoundaryDecision, evaluate_selection
from .controlled_client import AttemptRecord, ControlledAnalysisClient
from .external import (
    DEFAULT_ANALYZER_CLASS,
    DEFAULT_ANALYZER_MODULE,
    DISCLAIMER,
    ExternalAnalysisPort,
    ExternalAnalysisUnavailable,
    load_external_analyzer,
)
from .service import AnalysisOutcome, AnalysisService

__all__ = [
    "AnalysisOutcome",
    "AnalysisService",
    "AttemptRecord",
    "BoundaryDecision",
    "ControlledAnalysisClient",
    "DEFAULT_ANALYZER_CLASS",
    "DEFAULT_ANALYZER_MODULE",
    "DISCLAIMER",
    "ExternalAnalysisPort",
    "ExternalAnalysisUnavailable",
    "evaluate_selection",
    "load_external_analyzer",
]
