"""预置“三个室友的客厅”（PRD 3.1）。

文案来源规则（tasks/M01.md §3.6 I5／I6）：

- 人物设定／初始目标／私有背景只做**字段映射**，取自 PRD 3.1 的原文措辞；
- PRD 3.1 **未给出**陈禾的私有背景，因此该字段留空并在此注明——不编造具体私有事实；
- 表达习惯在 PRD 中没有独立描述，仅由“主动热情／表达直接／刚搬来”这类原文措辞
  推导为最小风格描述，可由操作者后续编辑；
- 默认不预设争吵、和解或最终决定（PRD 3.1）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import AgentProfileFields
from .contracts.limits import MAX_AGENT_NAME_CODEPOINTS


@dataclass(frozen=True)
class PresetAgent:
    """预置角色（模板五项内容的字面值）。"""

    name: str
    persona: str
    speech_style: str
    initial_goal: str
    private_background: str

    def to_profile(self) -> AgentProfileFields:
        return AgentProfileFields(
            name=self.name,
            persona=self.persona,
            speech_style=self.speech_style,
            initial_goal=self.initial_goal,
            private_background=self.private_background,
        )


@dataclass(frozen=True)
class PresetScene:
    """预置场景。"""

    key: str
    title: str
    background: str
    agents: tuple[PresetAgent, ...]


ROOMMATE_AGENTS: tuple[PresetAgent, ...] = (
    PresetAgent(
        name="安然",
        persona="主动热情，愿意张罗，喜欢把人凑到一起。",
        speech_style="热情、主动提问，句子偏长。",
        initial_goal="想找人一起度过晚上。",
        private_background="朋友临时取消了聚会。",
    ),
    PresetAgent(
        name="许川",
        persona="表达直接，不太绕弯子。",
        speech_style="短句、直接，少铺垫。",
        initial_goal="想休息。",
        private_background="今天工作很累。",
    ),
    PresetAgent(
        name="陈禾",
        persona="刚搬来，还是新面孔。",
        speech_style="客气、简短，先观察再开口。",
        initial_goal="想融入，但不想打扰别人。",
        # PRD 3.1 未给出陈禾的私有背景：留空，不编造具体私有事实。
        private_background="",
    ),
)

ROOMMATES = PresetScene(
    key="roommates",
    title="三个室友的客厅",
    background="晚上，三个室友在客厅相遇，尚未确定今晚做什么。",
    agents=ROOMMATE_AGENTS,
)

# ---------------------------------------------------------------------------
# 以下两个预置场景由**人工裁决**新增（决议记录见 state/STATUS.md B6 与
# state/reports/M07.md §6）：
#
#   PRD 第 10 节要求「预置三个场景各运行三次」，但第 3.1 节只定义了
#   「三个室友的客厅」这一个场景。项目负责人裁决为**补两个预置场景**，
#   而不是修改 PRD 表述。
#
# 这两组角色与场景是**项目自撰的虚构内容**，不得被表述为 PRD 的规定内容。
# 撰写时遵守与 PRD 3.1 相同的约束：
#   * 每个场景 3 名角色（PRD 默认三人，2～8 可配置）；
#   * 角色之间人物设定、表达习惯与当下目标互不相同，并各自保有私有背景；
#   * **不预设争吵、和解或最终决定**，也不指定谁必须达成什么。
# ---------------------------------------------------------------------------

STORE_AGENTS: tuple[PresetAgent, ...] = (
    PresetAgent(
        name="林小满",
        persona="便利店夜班店员，做事麻利，习惯把话说短。",
        speech_style="短句、先报事实，偶尔叹气。",
        initial_goal="想按点交接下班。",
        private_background="这个月房租还差一截，正在算能不能撑到发薪日。",
    ),
    PresetAgent(
        name="周远",
        persona="刚面试完的应聘者，礼貌但没什么兴致聊天。",
        speech_style="客气、回应简短，容易走神。",
        initial_goal="买瓶水就赶末班车。",
        private_background="今天的面试没通过，他没打算跟人提这件事。",
    ),
    PresetAgent(
        name="郑好",
        persona="便利店的常客，喜欢跟人搭话，不太会看气氛。",
        speech_style="话多、爱追问细节，语气轻快。",
        initial_goal="想找个人说说话。",
        private_background="刚搬到附近，认识的人很少，晚上常一个人待着。",
    ),
)

CONVENIENCE_STORE = PresetScene(
    key="convenience_store",
    title="深夜便利店的三个顾客",
    background="临近午夜，便利店里只有一名夜班店员和两位顾客，外面开始下雨。",
    agents=STORE_AGENTS,
)

CAMPSITE_AGENTS: tuple[PresetAgent, ...] = (
    PresetAgent(
        name="何澜",
        persona="被临时推举的带队人，认真但有点紧绷。",
        speech_style="喜欢先分工再说话，句子完整。",
        initial_goal="想在天黑前把营地安顿好。",
        private_background="第一次带队，心里没底，怕出错被人看出来。",
    ),
    PresetAgent(
        name="苏木",
        persona="露营新手，什么都想试一下。",
        speech_style="问题多、语气上扬，容易兴奋。",
        initial_goal="想学会搭帐篷。",
        private_background="报名时把自己的经验说得比实际多了一些。",
    ),
    PresetAgent(
        name="涂山",
        persona="常来露营的人，话不多，更愿意自己待着。",
        speech_style="慢、少、常以一句话结束话题。",
        initial_goal="想安静地钓一会儿鱼。",
        private_background="最近一直睡不好，出来是想换个环境。",
    ),
)

CAMPSITE = PresetScene(
    key="campsite",
    title="周末露营地的三个人",
    background="周末下午，三个人被分到同一块营地，装备已经卸在草地上。",
    agents=CAMPSITE_AGENTS,
)

PRESET_SCENES: dict[str, PresetScene] = {
    ROOMMATES.key: ROOMMATES,
    CONVENIENCE_STORE.key: CONVENIENCE_STORE,
    CAMPSITE.key: CAMPSITE,
}

DEFAULT_PRESET_KEY = ROOMMATES.key

#: 全部预置角色（按场景顺序）。模板名在本项目中全局唯一，因此各场景使用不同人名。
ALL_PRESET_AGENTS: tuple[PresetAgent, ...] = (
    ROOMMATE_AGENTS + STORE_AGENTS + CAMPSITE_AGENTS
)


def get_preset(key: str) -> PresetScene:
    """按键取预置场景；未知键抛出 ``KeyError`` 由调用方转成领域错误。"""

    return PRESET_SCENES[key]


def preset_agent_names(key: str = DEFAULT_PRESET_KEY) -> tuple[str, ...]:
    """某个预置场景的角色名（默认取「三个室友的客厅」）。"""

    return tuple(agent.name for agent in PRESET_SCENES[key].agents)


def preset_keys() -> tuple[str, ...]:
    return tuple(PRESET_SCENES)


# 预置名称必须符合契约长度上限；在导入时即校验，避免运行期才暴露。
for _agent in ALL_PRESET_AGENTS:
    assert len(_agent.name) <= MAX_AGENT_NAME_CODEPOINTS, _agent.name

# 预置角色名必须全局唯一：模板名唯一约束会拒绝重复（tasks/M01.md §3.6 I1）。
assert len({agent.name for agent in ALL_PRESET_AGENTS}) == len(ALL_PRESET_AGENTS), (
    "预置角色名重复，会导致模板创建失败"
)
