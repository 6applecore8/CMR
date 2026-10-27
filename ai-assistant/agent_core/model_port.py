"""模型端口先定义契约，不伪装已完成真实 Qwen 接入或自然语言理解。"""

from dataclasses import dataclass
from typing import Any, Protocol

from .contracts import DomainError


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


class ModelPlanner(Protocol):
    """模型只提出工具与参数；身份、业务时钟、权限由服务端决定。"""

    def plan(self, question: str) -> ToolCall: ...


class UnconfiguredModel:
    """默认关闭；测试直接构造 ToolCall，不冒充在线 AI。"""

    planned_model_id = "qwen3.8-max"

    def plan(self, question: str) -> ToolCall:
        raise DomainError("MODEL_NOT_CONFIGURED", "尚未接入真实模型，请使用规则联调入口", 503)
