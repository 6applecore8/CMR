"""客户只读工具。输入来自可信仓储，输出白名单字段，不暴露原始档案。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Sequence

from .contracts import DomainError, Principal, Role, result, text_arg, utc_now, validate_args


@dataclass(frozen=True)
class Customer:
    """仓储映射后的记录；历史资料归属未确认时不得自动扩大访问范围。"""

    client_id: str
    tenant_id: str
    owner_id: str | None
    company: str = ""
    contact_name: str = ""
    tier: str = ""
    channel: str = "email"
    address: str = ""
    requirement: str = ""
    status: str = "new"
    deleted: bool = False

    def __post_init__(self) -> None:
        for key in ("client_id", "tenant_id"):
            value = getattr(self, key)
            if text_arg(value, key, required=True) != value:
                raise DomainError("SOURCE_INCONSISTENT", "客户标识需要规范值", 503)
        if self.owner_id is not None:
            if text_arg(self.owner_id, "ownerId", required=True) != self.owner_id:
                raise DomainError("SOURCE_INCONSISTENT", "客户归属需要规范值", 503)
        if self.tier not in {"", "A", "B", "C"} or self.channel not in {"email", "alibaba"} or type(self.deleted) is not bool:
            raise DomainError("SOURCE_INCONSISTENT", "客户主源字段类型或枚举异常", 503)
        if any(not isinstance(v, str) for v in (self.company, self.contact_name, self.address, self.requirement, self.status)):
            raise DomainError("SOURCE_INCONSISTENT", "客户主源文本字段类型异常", 503)


def can_read(principal: Principal, customer: Customer) -> bool:
    """先限定组织，再限定负责人；此处不是用姓名或模糊相似度鉴权。"""
    return (
        not customer.deleted
        and customer.tenant_id == principal.tenant_id
        and (principal.role is Role.MANAGER or customer.owner_id == principal.user_id)
    )


class CustomerTools:
    """把统计、搜索和详情封装为有限工具；不会执行模型提供的 SQL。"""

    def __init__(self, reader: Callable[[], Sequence[Customer]], clock: Callable[[], datetime] = utc_now):
        self._reader, self._clock = reader, clock

    def execute(self, tool: str, args: Mapping[str, Any], principal: Principal, trace_id: str) -> dict:
        """执行授权查询；仓储异常直接向上传递，不能变成正常的零条结果。"""
        if tool not in {"count_customers", "search_customers", "get_customer_detail"}:
            raise DomainError("UNKNOWN_TOOL", "不支持该客户工具")
        allowed = {"clientId"} if tool == "get_customer_detail" else {"tier", "channel"}
        if tool == "search_customers":
            allowed |= {"keyword", "page", "size"}
        params = validate_args(args, allowed)
        # 参数先校验，失败时不必读取敏感仓储。
        client_id = text_arg(params.get("clientId", ""), "clientId", required=True) if tool == "get_customer_detail" else ""
        tier = text_arg(params.get("tier", ""), "tier")
        channel = text_arg(params.get("channel", "all"), "channel")
        keyword = text_arg(params.get("keyword", ""), "keyword")
        if tier not in {"", "A", "B", "C"} or channel not in {"all", "alibaba", "email"}:
            raise DomainError("INVALID_ARGUMENT", "等级或渠道不在允许范围内")
        page, size = params.get("page", 1), params.get("size", 20)
        if type(page) is not int or not 1 <= page <= 10000 or type(size) is not int or not 1 <= size <= 50:
            raise DomainError("INVALID_ARGUMENT", "分页参数超出允许范围")
        records = [c for c in self._reader() if c.tenant_id == principal.tenant_id]
        if len({(c.tenant_id, c.client_id) for c in records}) != len(records):
            raise DomainError("SOURCE_INCONSISTENT", "客户主源存在重复记录，需管理员检查", 503)
        visible = [c for c in records if can_read(principal, c)]
        meta = {
            "asOf": self._clock().isoformat(), "source": "customer_repository",
            "scope": "organization" if principal.role is Role.MANAGER else "owned",
        }
        if tool == "get_customer_detail":
            customer = next((c for c in visible if c.client_id == client_id), None)
            if customer is None:
                # 无权限和不存在返回相同结果，避免探测其他员工的客户 ID。
                raise DomainError("CUSTOMER_NOT_FOUND", "未找到可访问的客户", 404)
            data = self._summary(customer)
            data.update(address=customer.address or None, requirement=customer.requirement or None)
            return result({"kind": "customer_detail", "state": "OK", "customer": data, **meta}, trace_id)
        filtered = [c for c in visible if (not tier or c.tier == tier) and (channel == "all" or c.channel == channel)]
        if keyword:
            filtered = [c for c in filtered if keyword.casefold() in " ".join((c.company, c.contact_name, c.requirement)).casefold()]
        filters = {"tier": tier or None, "channel": channel}
        if tool == "count_customers":
            return result({"kind": "customer_count", "state": "OK", "count": len(filtered), "filters": filters, **meta}, trace_id)
        filtered.sort(key=lambda c: c.client_id)
        items = [self._summary(c) for c in filtered[(page - 1) * size:page * size]]
        return result({
            "kind": "customer_search", "state": "OK" if filtered else "NOT_FOUND",
            "items": items, "total": len(filtered), "page": page, "size": size,
            "requiresSelection": len(filtered) > 1, "filters": filters, **meta,
        }, trace_id)

    @staticmethod
    def _summary(customer: Customer) -> dict:
        """列表不含地址、原始 Markdown、内部备注或完整联系方式。"""
        return {
            "clientId": customer.client_id, "company": customer.company,
            "contactName": customer.contact_name, "tier": customer.tier,
            "channel": customer.channel, "status": customer.status,
        }
