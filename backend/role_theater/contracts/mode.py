"""薄模式配置。公共文本沿用场景预算，参与者配置仅本人可见。"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator, model_validator

from .enums import SceneMode
from .limits import MAX_SCENE_BACKGROUND_CODEPOINTS

PublicText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
TopicText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
FocusText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
PositionText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class SimulationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    situation: PublicText = ""
    public_information: PublicText = ""

    @model_validator(mode="after")
    def _total(self):
        if len(self.background_text()) > MAX_SCENE_BACKGROUND_CODEPOINTS:
            raise ValueError("情境与公共信息合计不能超过 2000 个 Unicode 码点")
        return self

    def background_text(self) -> str:
        return "\n".join(value for value in (self.situation, self.public_information) if value)


class DiscussionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic: TopicText
    materials: PublicText = ""

    @model_validator(mode="after")
    def _total(self):
        if len(self.background_text()) > MAX_SCENE_BACKGROUND_CODEPOINTS:
            raise ValueError("议题与材料合计不能超过 2000 个 Unicode 码点")
        return self

    def background_text(self) -> str:
        return "\n".join(value for value in (self.topic, self.materials) if value)


class DiscussionParticipantConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    focus: FocusText = ""
    initial_position: PositionText | None = None

    @field_validator("initial_position", mode="before")
    @classmethod
    def _empty_position(cls, value):
        return None if isinstance(value, str) and not value.strip() else value


def resolve_mode_config(mode: SceneMode, config, background: str):
    """旧入站仅有 background；新入站禁止跨模式和矛盾的双重输入。"""
    if config is None:
        if mode is SceneMode.DISCUSSION:
            raise ValueError("discussion 必须提供议题配置")
        config = SimulationConfig(situation=background)
    expected = SimulationConfig if mode is SceneMode.SIMULATION else DiscussionConfig
    if not isinstance(config, expected):
        raise ValueError("模式与配置不一致")
    if background and background != config.background_text():
        raise ValueError("background 与模式配置不一致")
    return config
