"""标识符类型。

M00 不固定 ID 生成算法（PRD 未规定），只约束为：裁剪空白后的非空短字符串。
真正的 ID 生成在 M01（模板／场景／角色）与 M04（事件／行动／消息）实现。
"""

from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints

from .limits import MAX_ID_CODEPOINTS

IdStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_ID_CODEPOINTS),
]

SceneId = IdStr
AgentId = IdStr
MessageId = IdStr
EventId = IdStr
TemplateId = IdStr
RequestId = IdStr
TurnId = IdStr
AttemptId = IdStr
ActionId = IdStr
AnalysisId = IdStr
