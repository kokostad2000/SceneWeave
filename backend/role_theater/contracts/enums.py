"""契约枚举。前后端共享的唯一取值来源（PRD 第 8 节）。

新增模块只能在此文件扩展枚举，并通过 OpenAPI 生成前端类型；不得在前后端
各自维护一套取值。
"""

from __future__ import annotations

from enum import StrEnum


class ActionType(StrEnum):
    """模型只能返回的行动类型（PRD 4.2）。"""

    SPEAK = "SPEAK"
    PASS = "PASS"


class EventVisibility(StrEnum):
    """人工事件可见范围（PRD 4.3）。"""

    ALL = "ALL"
    TARGETED = "TARGETED"


class EventStatus(StrEnum):
    """界面必须区分“已接受”和“已生效”（PRD 4.3）。"""

    ACCEPTED = "ACCEPTED"
    EFFECTIVE = "EFFECTIVE"


class RunState(StrEnum):
    """会话运行状态（PRD 5.2）。没有其他状态。"""

    READY = "READY"
    RUNNING = "RUNNING"
    PAUSING = "PAUSING"
    STOPPING = "STOPPING"
    PAUSED = "PAUSED"
    ENDED = "ENDED"


class PauseReason(StrEnum):
    """暂停原因必须区分（PRD 5.2）。"""

    NO_NEW_INFORMATION = "NO_NEW_INFORMATION"
    MANUAL = "MANUAL"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    CONTEXT_LIMIT = "CONTEXT_LIMIT"
    PROCESS_INTERRUPT = "PROCESS_INTERRUPT"


class ControlCommandType(StrEnum):
    """控制命令类型（PRD 5.2）。"""

    START = "START"
    STEP = "STEP"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    STOP = "STOP"


class TurnStatus(StrEnum):
    """一次角色调用的落盘结果；只有 SUCCEEDED 才推进已处理位置（PRD 5.1）。"""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class ModelFailureKind(StrEnum):
    """模型调用的失败分类（PRD 4.2 / 5.2 / 5.3）。

    UNKNOWN_REQUEST / 发送结果不明时保守占用预算并标记 UNKNOWN（PRD 5.3）。
    """

    EMPTY_CONTENT = "EMPTY_CONTENT"
    TRUNCATED = "TRUNCATED"
    INVALID_JSON = "INVALID_JSON"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    REFERENCE_INVALID = "REFERENCE_INVALID"
    TIMEOUT = "TIMEOUT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    CONTEXT_LIMIT = "CONTEXT_LIMIT"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    #: 缺少模型配置（密钥或基地址），**尚未发送**，不新增模型请求（PRD 5.3）。
    MISSING_CONFIG = "MISSING_CONFIG"
    UNKNOWN_REQUEST = "UNKNOWN_REQUEST"
    #: 本地校验拒绝发送（如入站参数非法）——同样不新增模型请求（PRD 5.3）。
    NOT_DISPATCHED = "NOT_DISPATCHED"


class AnalysisStatus(StrEnum):
    """五种结果状态必须区分（PRD 6.2）。"""

    NORMAL = "NORMAL"
    BLOCKED = "BLOCKED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    DISABLED = "DISABLED"


class SchedulerReason(StrEnum):
    """调度结果可复核（PRD 5.1）。"""

    STARTUP_OPPORTUNITY = "STARTUP_OPPORTUNITY"
    NEW_VISIBLE_INFORMATION = "NEW_VISIBLE_INFORMATION"
    REQUESTED_SPEAKER_PRIORITY = "REQUESTED_SPEAKER_PRIORITY"
    ROUND_ROBIN = "ROUND_ROBIN"
