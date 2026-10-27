"""固定工具路由；模型输出不能调用任意函数、SQL 或管理动作。"""

from .contracts import DomainError, Principal
from .customers import CustomerTools
from .model_port import ToolCall
from .pricing import PricingTools


class ToolDispatcher:
    """认证上下文由调用方绑定；本阶段仅供测试，不是公开 HTTP 入口。"""

    def __init__(self, customers: CustomerTools, pricing: PricingTools):
        self.customers, self.pricing = customers, pricing

    def execute(self, call: ToolCall, principal: Principal, trace_id: str) -> dict:
        """仅路由允许的只读工具，异常应由未来 HTTP 层统一映射并脱敏记录。"""
        if call.name == "get_current_price":
            return self.pricing.execute(call.arguments, principal, trace_id)
        if call.name in {"count_customers", "search_customers", "get_customer_detail"}:
            return self.customers.execute(call.name, call.arguments, principal, trace_id)
        raise DomainError("UNKNOWN_TOOL", "该工具不在只读白名单中")
