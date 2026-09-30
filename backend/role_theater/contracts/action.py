"""角色行动契约（PRD 4.2）。

分工必须保持：模型只返回 :class:`ActionDraft` 的五个字段；``actor_id``／
``scene_id``／消息 ID／时间由服务端添加。契约层只做**结构校验**，不静默修剪
文本、不自动广播、不追加修复调用。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from .enums import ActionType, TurnStatus
from .ids import ActionId, AgentId, AttemptId, MessageId, SceneId, TurnId
from .limits import (
    MAX_SPEAK_TEXT_CODEPOINTS,
    LEGACY_SPEAK_TEXT_CODEPOINTS,
    MIN_SPEAK_TEXT_CODEPOINTS,
    codepoint_length,
)


class ActionDraft(BaseModel):
    """模型一次调用唯一允许返回的结构。

    ``extra="forbid"``：出现额外字段即失败（``SCHEMA_INVALID``），不忽略。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: ActionType
    text: str = ""
    reply_to_message_id: MessageId | None = None
    requested_speaker_id: AgentId | None = None
    recipient_id: AgentId | None = None

    @field_validator("text", mode="before")
    @classmethod
    def _strip_text(cls, value: object) -> object:
        # 空白裁剪后再校验长度（PRD 3.3）。
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _check_protocol(self, info: ValidationInfo) -> ActionDraft:
        if self.action is ActionType.PASS:
            if self.text != "" or self.reply_to_message_id is not None or self.requested_speaker_id is not None or self.recipient_id is not None:
                raise ValueError(
                    "PASS 要求 text 与 reply_to_message_id、requested_speaker_id 均为空"
                )
            return self

        if self.action is ActionType.PRIVATE:
            if self.recipient_id is None or self.requested_speaker_id is not None:
                raise ValueError("PRIVATE 必须有 recipient_id 且 requested_speaker_id 为空")
        elif self.recipient_id is not None:
            raise ValueError("SPEAK 的 recipient_id 必须为空")

        length = codepoint_length(self.text)
        if length < MIN_SPEAK_TEXT_CODEPOINTS:
            raise ValueError("SPEAK 的 text 不能为空")
        limit = LEGACY_SPEAK_TEXT_CODEPOINTS if (info.context or {}).get("chat_policy_version") == 1 else MAX_SPEAK_TEXT_CODEPOINTS
        if length > limit:
            raise ValueError(
                f"SPEAK 的 text 不能超过 {limit} 个 Unicode 码点，"
                f"实际 {length}"
            )
        return self


class ActionRecord(BaseModel):
    """一次角色调用的落盘结果。

    只有 ``SUCCEEDED`` 的 SPEAK／PRIVATE／PASS 才推进该角色的已处理位置；失败不推进
    （PRD 5.1）。``input_cursor_seq`` 记录本次调用使用的输入快照截止序号。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    action_id: ActionId
    turn_id: TurnId
    attempt_id: AttemptId
    scene_id: SceneId
    actor_id: AgentId
    status: TurnStatus
    draft: ActionDraft | None = None
    message_id: MessageId | None = None
    input_cursor_seq: int = Field(ge=0)
    prompt_template_id: str = Field(min_length=1)
    created_at: datetime

    @model_validator(mode="after")
    def _check_consistency(self) -> ActionRecord:
        if self.status is TurnStatus.SUCCEEDED:
            if self.draft is None:
                raise ValueError("SUCCEEDED 必须携带 draft")
        elif self.draft is not None:
            raise ValueError("非 SUCCEEDED 的行动不得携带 draft")
        if self.message_id is not None:
            if self.draft is None or self.draft.action not in (ActionType.SPEAK, ActionType.PRIVATE):
                raise ValueError("只有成功的 SPEAK／PRIVATE 才产生 message_id")
        return self
