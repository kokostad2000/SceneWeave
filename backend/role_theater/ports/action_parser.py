"""行动内容的解析与校验（PRD 4.2、5.3）。

纯函数：输入是模型返回的 `content` 文本与允许的引用范围，输出是
`ActionDraft` 或结构化 `ModelFailure`。**不做任何静默修剪、不自动广播、不追加
修复调用**——空 content、截断、非法 JSON、字段非法、引用非法一律失败。
"""

from __future__ import annotations

import json

from ..contracts import (
    ActionDraft,
    ModelFailure,
    ModelFailureKind,
    ReferenceScope,
)
from pydantic import ValidationError

#: 只允许这四个字段（PRD 4.2：模型只返回 action／text／两个引用）。
ALLOWED_FIELDS = frozenset({"action", "text", "reply_to_message_id", "requested_speaker_id"})

#: 官方文档中表示“服务端未正常完成”的 ``finish_reason`` 取值及其失败分类。
#: 来源：DeepSeek Chat Completions API 文档（见 docs/SOURCES.md）。
FINISH_REASON_FAILURES: dict[str, ModelFailureKind] = {
    "length": ModelFailureKind.TRUNCATED,
    "content_filter": ModelFailureKind.PROVIDER_ERROR,
    "insufficient_system_resource": ModelFailureKind.PROVIDER_ERROR,
    "aborted": ModelFailureKind.PROVIDER_ERROR,
    "tool_calls": ModelFailureKind.PROVIDER_ERROR,
}

FINISH_REASON_DETAILS: dict[str, str] = {
    "length": "finish_reason=length：输出因 max_tokens 或上下文上限被截断",
    "content_filter": "finish_reason=content_filter：内容被服务端内容过滤，未返回完整内容",
    "insufficient_system_resource": "finish_reason=insufficient_system_resource：推理资源不足，生成被中断",
    "aborted": "finish_reason=aborted：生成被中断",
    "tool_calls": "finish_reason=tool_calls：模型请求调用工具，但本项目不发送 tools（PRD 2.2）",
}

#: 正常结束的取值（``stop`` 表示自然结束或命中 stop 序列）。
NORMAL_FINISH_REASONS = frozenset({"stop", None})


def validate_references(draft: ActionDraft, scope: ReferenceScope | None) -> ModelFailure | None:
    """校验引用是否落在合法范围内（PRD 4.2）。返回 None 表示通过。"""

    if scope is None:
        return None

    if draft.reply_to_message_id is not None:
        if draft.reply_to_message_id not in set(scope.allowed_message_ids):
            return ModelFailure(
                kind=ModelFailureKind.REFERENCE_INVALID,
                detail=f"reply_to_message_id 不是本场已提交且该角色可见的公开发言："
                f"{draft.reply_to_message_id}",
            )

    if draft.requested_speaker_id is not None:
        if draft.requested_speaker_id == scope.actor_id:
            return ModelFailure(
                kind=ModelFailureKind.REFERENCE_INVALID,
                detail="requested_speaker_id 不能指向自己",
            )
        if draft.requested_speaker_id not in set(scope.allowed_speaker_ids):
            return ModelFailure(
                kind=ModelFailureKind.REFERENCE_INVALID,
                detail=f"requested_speaker_id 不是本场其他有效角色：{draft.requested_speaker_id}",
            )

    return None


def parse_action_content(
    content: str | None,
    *,
    finish_reason: str | None = None,
    scope: ReferenceScope | None = None,
) -> ActionDraft | ModelFailure:
    """把模型返回的文本解析为行动草稿或失败分类。

    分类优先级（按官方 Chat Completions 文档核对后的顺序）：
    **服务端未正常完成** → 空 content → 非法 JSON → 字段／长度非法 → 引用非法。

    ``finish_reason`` 的取值来自官方文档：``stop``／``length``／``content_filter``／
    ``tool_calls``／``insufficient_system_resource``／``aborted``。除 ``stop`` 外的
    异常取值必须在解析内容**之前**判定——此时 content 往往为空或残缺，先判原因才能
    给出可解释的失败，而不是笼统的“空 content”。
    """

    # 1) 服务端未正常完成：先按 finish_reason 给出可解释的失败。
    if finish_reason in FINISH_REASON_FAILURES:
        return ModelFailure(
            kind=FINISH_REASON_FAILURES[finish_reason],
            detail=FINISH_REASON_DETAILS[finish_reason],
        )

    # 2) 正常结束但没有内容。
    if content is None or not content.strip():
        return ModelFailure(kind=ModelFailureKind.EMPTY_CONTENT, detail="模型返回空 content")

    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, ValueError) as exc:
        return ModelFailure(kind=ModelFailureKind.INVALID_JSON, detail=f"非法 JSON：{exc}")

    if not isinstance(payload, dict):
        return ModelFailure(
            kind=ModelFailureKind.SCHEMA_INVALID,
            detail=f"顶层必须是 JSON 对象，实际是 {type(payload).__name__}",
        )

    extra = sorted(set(payload) - ALLOWED_FIELDS)
    if extra:
        return ModelFailure(
            kind=ModelFailureKind.SCHEMA_INVALID,
            detail=f"出现不允许的字段：{', '.join(extra)}",
        )

    missing = {"action"} - set(payload)
    if missing:
        return ModelFailure(
            kind=ModelFailureKind.SCHEMA_INVALID,
            detail=f"缺少必需字段：{', '.join(sorted(missing))}",
        )

    try:
        draft = ActionDraft.model_validate(payload)
    except ValidationError as exc:
        return ModelFailure(kind=ModelFailureKind.SCHEMA_INVALID, detail=str(exc))

    reference_failure = validate_references(draft, scope)
    if reference_failure is not None:
        return reference_failure

    return draft


__all__ = [
    "ALLOWED_FIELDS",
    "FINISH_REASON_DETAILS",
    "FINISH_REASON_FAILURES",
    "NORMAL_FINISH_REASONS",
    "parse_action_content",
    "validate_references",
]
