"""可信后端的问数组合服务；不是 HTTP 路由，也不提供登录能力。"""

from .contracts import DomainError, Principal
from .deepseek import validate_tool_call
from .dispatcher import ToolDispatcher
from .model_port import ModelPlanner


class QueryService:
    """将模型计划交给确定性工具；查询事实不回传模型做二次改写。"""

    def __init__(self, planner: ModelPlanner, dispatcher: ToolDispatcher):
        self._planner, self._dispatcher = planner, dispatcher

    def ask(self, question: str, principal: Principal, trace_id: str) -> dict:
        """身份来自服务端认证层；返回原工具响应，保留权限、来源和报价时效规则。"""
        if not isinstance(principal, Principal):
            raise DomainError("INVALID_PRINCIPAL", "需要有效的员工身份", 401)
        call = self._planner.plan(question, trace_id=trace_id)
        validate_tool_call(call)
        return self._dispatcher.execute(call, principal, trace_id)
