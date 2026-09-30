"""行动内容的解析与校验（PRD 4.2、5.3）。

纯函数：输入是模型返回的 `content` 文本与允许的引用范围，输出是
`ActionDraft` 或结构化 `ModelFailure`。**不做任何静默修剪、不自动广播、不追加
修复调用**——空 content、截断、非法 JSON、字段非法、引用非法一律失败。

唯一的归一化是**引用别名解析**：提示词用 ``[#序号]`` 展示发言，模型可能直接回
序号，因此 ``ReferenceScope.allowed_message_seqs`` 里的序号会被确定性地换算成
对应的真实消息 ID。这是查表换算，不是修剪或修复调用：序号不在表内依旧是非法引用。
"""

from __future__ import annotations

import json
import re

from ..contracts import (
    ActionType,
    ActionDraft,
    ModelFailure,
    ModelFailureKind,
    ReferenceScope,
)
from pydantic import ValidationError
from ..contracts.limits import LEGACY_SPEAK_TEXT_CODEPOINTS, MAX_SPEAK_TEXT_CODEPOINTS

#: 只允许五个字段（PRD 4.2），身份和频道标识由服务端决定。
ALLOWED_FIELDS = frozenset({"action", "text", "reply_to_message_id", "requested_speaker_id", "recipient_id"})

#: 提示词里的发言编号写法：``3``／``"3"``／``"#3"``／``"[#3]"`` 都指同一条发言。
_SEQ_ALIAS = re.compile(r"^\[?#?(\d+)\]?$")

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


def validate_references(draft: ActionDraft, scope: ReferenceScope | None, *, chat_policy_version: int | None = None) -> ModelFailure | None:
    """校验引用是否落在合法范围内（PRD 4.2）。返回 None 表示通过。"""

    policy = chat_policy_version if chat_policy_version is not None else (scope.chat_policy_version if scope else 1)
    limit = MAX_SPEAK_TEXT_CODEPOINTS if policy == 2 else LEGACY_SPEAK_TEXT_CODEPOINTS
    if len(draft.text) > limit:
        return ModelFailure(kind=ModelFailureKind.SCHEMA_INVALID,
                            detail=f"正文超过本场 {limit} 个 Unicode 码点上限")

    if scope is None:
        return None

    if draft.recipient_id is not None:
        if draft.recipient_id == scope.actor_id or draft.recipient_id not in scope.allowed_speaker_ids:
            return ModelFailure(kind=ModelFailureKind.REFERENCE_INVALID, detail="私聊收件人必须是本场另一角色")
    if draft.reply_to_message_id is not None:
        if draft.action is ActionType.PRIVATE:
            valid = scope.received_private_messages.get(draft.reply_to_message_id) == draft.recipient_id
        else:
            valid = draft.reply_to_message_id in scope.allowed_message_ids
        if not valid:
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


def resolve_message_alias(value: object, scope: ReferenceScope | None) -> object:
    """把发言序号别名换算成真实消息 ID（PRD 4.2）。

    接受 ``3``／``"3"``／``"#3"``／``"[#3]"``——都是提示词 ``[#3]`` 的自然写法。
    换算只在 ``scope`` 给出序号表时发生；换算不了的值原样返回，交给后续校验给出
    明确的失败分类（无法解析的类型仍是 ``SCHEMA_INVALID``，序号越界是
    ``REFERENCE_INVALID``）。
    """

    if scope is None or not (scope.allowed_message_seqs or scope.private_message_seqs):
        return value

    seq: int | None = None
    if isinstance(value, bool):  # bool 是 int 子类，但真／假不是序号。
        return value
    if isinstance(value, int):
        seq = value
    elif isinstance(value, str):
        matched = _SEQ_ALIAS.match(value.strip())
        if matched:
            seq = int(matched.group(1))

    if seq is None:
        return value

    resolved = scope.allowed_message_seqs.get(seq) or scope.private_message_seqs.get(seq)
    if resolved is not None:
        return resolved
    # 序号越界：转成字符串，让引用校验而不是字段类型来报告这个错误。
    return str(seq)


def parse_action_content(
    content: str | None,
    *,
    finish_reason: str | None = None,
    scope: ReferenceScope | None = None,
    chat_policy_version: int | None = None,
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

    # 引用别名归一化：``reply_to_message_id`` 写序号时换算成真实消息 ID。
    # 其余字段一律不动，避免任何“顺手修好”的宽松行为。
    if "reply_to_message_id" in payload:
        resolved = resolve_message_alias(payload["reply_to_message_id"], scope)
        if resolved is not payload["reply_to_message_id"]:
            payload = {**payload, "reply_to_message_id": resolved}

    try:
        draft = ActionDraft.model_validate(payload, context={
            "chat_policy_version": chat_policy_version if chat_policy_version is not None else
                scope.chat_policy_version if scope is not None else 1,
        })
    except ValidationError as exc:
        return ModelFailure(kind=ModelFailureKind.SCHEMA_INVALID, detail=str(exc))

    reference_failure = validate_references(draft, scope, chat_policy_version=chat_policy_version)
    if reference_failure is not None:
        return reference_failure

    return draft


__all__ = [
    "ALLOWED_FIELDS",
    "FINISH_REASON_DETAILS",
    "FINISH_REASON_FAILURES",
    "NORMAL_FINISH_REASONS",
    "parse_action_content",
    "resolve_message_alias",
    "validate_references",
]
