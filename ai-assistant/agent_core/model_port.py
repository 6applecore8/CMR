"""模型端口契约；在线适配见 deepseek.py，不在领域工具中持有密钥。"""

from dataclasses import dataclass
from typing import Any, Protocol

from .contracts import DomainError


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


class ModelPlanner(Protocol):
    """模型只提出工具与参数；身份、业务时钟、权限由服务端决定。"""

    def plan(self, question: str, *, trace_id: str | None = None) -> ToolCall: ...


class UnconfiguredModel:
    """默认关闭；测试直接构造 ToolCall，不冒充在线 AI。"""

    planned_model_id = "deepseek-flash"

    def plan(self, question: str, *, trace_id: str | None = None) -> ToolCall:
        raise DomainError("MODEL_NOT_CONFIGURED", "尚未接入真实模型，请使用规则联调入口", 503)
