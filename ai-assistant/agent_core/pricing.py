"""确定性的报价选择与政策规则；历史金额永远不冒充当前报价。"""

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import re
from typing import Any, Callable, Mapping, Sequence

from .contracts import DomainError, Principal, result, text_arg, validate_args
from .customers import Customer, can_read


def business_today() -> date:
    """报价日期按中国业务时区计算，不能依赖部署机器的本地时区。"""
    return datetime.now(timezone(timedelta(hours=8))).date()


def _positive_decimal(value: Any, name: str) -> Decimal:
    """只接受精确十进制，避免二进制浮点金额或 NaN 绕过比较。"""
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise DomainError("INVALID_PRICE_DATA", f"{name} 必须为正的精确十进制数")
    return value


@dataclass(frozen=True)
class PriceScope:
    """构成价格适用范围的显式维度；不以相似名称代替产品唯一标识。"""

    product_id: str
    specification: str
    currency: str
    unit: str
    trade_term: str
    customer_id: str | None = None

    def __post_init__(self) -> None:
        for key in ("product_id", "specification", "currency", "unit", "trade_term"):
            value = getattr(self, key)
            if text_arg(value, key, required=True) != value:
                raise DomainError("INVALID_ARGUMENT", "价格条件需要使用规范值")
        if not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise DomainError("INVALID_ARGUMENT", "币种需要三位大写代码")
        if self.customer_id is not None:
            if text_arg(self.customer_id, "customerId", required=True) != self.customer_id:
                raise DomainError("INVALID_PRICE_DATA", "客户标识需要规范值")


@dataclass(frozen=True)
class PriceVersion:
    """已保存的不可变版本。审批/撤回的持久化事务在后续服务层实现。"""

    price_id: str
    tenant_id: str
    scope: PriceScope
    revision: int
    amount: Decimal
    min_quantity: Decimal
    max_quantity: Decimal | None
    issued_on: date
    valid_from: date
    valid_until: date | None
    status: str
    approved_on: date | None
    source_ref: str
    supersedes_id: str | None = None

    def __post_init__(self) -> None:
        for key in ("price_id", "tenant_id", "source_ref"):
            text_arg(getattr(self, key), key, required=True, limit=300)
        if type(self.revision) is not int or self.revision < 1:
            raise DomainError("INVALID_PRICE_DATA", "价格修订号必须为正整数")
        _positive_decimal(self.amount, "价格")
        _positive_decimal(self.min_quantity, "最小数量")
        if self.max_quantity is not None:
            _positive_decimal(self.max_quantity, "最大数量")
            if self.max_quantity <= self.min_quantity:
                raise DomainError("INVALID_PRICE_DATA", "数量档位必须为非空的左闭右开区间")
        if type(self.issued_on) is not date or type(self.valid_from) is not date:
            raise DomainError("INVALID_PRICE_DATA", "报价日期类型无效")
        if self.issued_on > self.valid_from:
            raise DomainError("INVALID_PRICE_DATA", "生效日期不能早于报价发布日期")
        if self.valid_until is not None and (type(self.valid_until) is not date or self.valid_until <= self.valid_from):
            raise DomainError("INVALID_PRICE_DATA", "截止日期必须晚于生效日期")
        if self.status not in {"draft", "approved", "revoked"}:
            raise DomainError("INVALID_PRICE_DATA", "未知报价状态")
        if self.status in {"approved", "revoked"} and (
            type(self.approved_on) is not date or self.approved_on < self.issued_on
        ):
            raise DomainError("INVALID_PRICE_DATA", "已发布报价需要有效审批日期")


@dataclass(frozen=True)
class PricingPolicy:
    """组织级规则快照；年份约束只用于报价，不过滤专业知识。"""

    tenant_id: str
    version: int = 1
    minimum_year: int | None = 2026
    review_after_days: int | None = None
    allow_history: bool = True

    def __post_init__(self) -> None:
        text_arg(self.tenant_id, "tenantId", required=True)
        if type(self.version) is not int or self.version < 1:
            raise DomainError("INVALID_POLICY", "政策版本必须为正整数")
        if self.minimum_year is not None and (type(self.minimum_year) is not int or not 1900 <= self.minimum_year <= 9999):
            raise DomainError("INVALID_POLICY", "年份门槛无效")
        if self.review_after_days is not None and (type(self.review_after_days) is not int or not 1 <= self.review_after_days <= 3650):
            raise DomainError("INVALID_POLICY", "复核周期必须为 1 至 3650 天")
        if type(self.allow_history) is not bool:
            raise DomainError("INVALID_POLICY", "历史查看开关必须为布尔值")


def change_policy(principal: Principal, current: PricingPolicy, changes: Mapping[str, Any], expected_version: int) -> PricingPolicy:
    """校验管理权限与乐观锁后产生新快照；调用方仍需事务保存并写审计。"""
    principal.require_manager()
    if principal.tenant_id != current.tenant_id:
        raise DomainError("FORBIDDEN", "不能修改其他组织政策", 403)
    if type(expected_version) is not int or expected_version != current.version:
        raise DomainError("POLICY_VERSION_CONFLICT", "政策已变化，请刷新后重试", 409)
    fields = validate_args(changes, {"minimum_year", "review_after_days", "allow_history"})
    if not fields:
        raise DomainError("INVALID_POLICY", "没有需要修改的政策字段")
    return replace(current, version=current.version + 1, **fields)


class PricingTools:
    """查询当前适用报价；不支持通过模型参数设置日期、权限或降级规则。"""

    def __init__(
        self,
        price_reader: Callable[[], Sequence[PriceVersion]],
        customer_reader: Callable[[], Sequence[Customer]],
        policy_reader: Callable[[], PricingPolicy],
        clock: Callable[[], date] = business_today,
    ):
        self._prices, self._customers, self._policy, self._clock = price_reader, customer_reader, policy_reader, clock

    def execute(self, args: Mapping[str, Any], principal: Principal, trace_id: str) -> dict:
        """执行一次确定性选择，仓储错误不转换为“没有报价”。"""
        params = validate_args(args, {"productId", "specification", "currency", "unit", "tradeTerm", "quantity", "customerId"})
        fields = {
            key: text_arg(params.get(key, ""), key, required=True)
            for key in ("productId", "specification", "currency", "unit", "tradeTerm")
        }
        raw_quantity = text_arg(params.get("quantity", ""), "quantity", required=True, limit=40)
        # 请求传十进制字符串，不接受 float、科学记数或特殊值。
        if not re.fullmatch(r"\d+(?:\.\d+)?", raw_quantity):
            raise DomainError("INVALID_ARGUMENT", "quantity 需要十进制数量文本")
        quantity = _positive_decimal(Decimal(raw_quantity), "数量")
        customer_id = params.get("customerId")
        if customer_id is not None:
            customer_id = text_arg(customer_id, "customerId", required=True)
            if not any(c.client_id == customer_id and can_read(principal, c) for c in self._customers()):
                raise DomainError("CUSTOMER_NOT_FOUND", "未找到可访问的客户", 404)
        scope = PriceScope(fields["productId"], fields["specification"], fields["currency"], fields["unit"], fields["tradeTerm"], customer_id)
        policy, today = self._policy(), self._clock()
        if policy.tenant_id != principal.tenant_id:
            raise DomainError("INVALID_POLICY", "组织政策读取异常", 503)
        prices = [p for p in self._prices() if p.tenant_id == principal.tenant_id]
        meta = {
            "kind": "current_price", "asOf": today.isoformat(), "policyVersion": policy.version,
            "source": "price_repository", "canQuote": False, "currentPrice": None,
        }
        if len({p.price_id for p in prices}) != len(prices):
            return self._review(meta, "DUPLICATE_PRICE_ID", trace_id)
        candidates = [p for p in prices if self._matches(p, scope, quantity)]
        # 未来生效/未来审批的报价不参与替代；草稿也不能抢占已发布版本。
        published = [p for p in candidates if p.status in {"approved", "revoked"}
                     and p.approved_on <= today and p.valid_from <= today]
        if not published:
            return self._review(meta, "NO_PUBLISHED_PRICE", trace_id)
        specific = [p for p in published if p.scope.customer_id == customer_id and customer_id is not None]
        selected_scope = specific or [p for p in published if p.scope.customer_id is None]
        if not selected_scope:
            return self._review(meta, "NO_APPLICABLE_PRICE", trace_id)
        meta["historyAvailable"] = policy.allow_history and bool(selected_scope)
        # 重叠档位不以“便宜优先”猜测业务规则，必须让管理层澄清。
        bands = {(p.min_quantity, p.max_quantity) for p in selected_scope}
        if len(bands) != 1:
            return self._review(meta, "OVERLAPPING_QUANTITY_BANDS", trace_id)
        by_id = {p.price_id: p for p in prices}
        replaced: set[str] = set()
        for version in selected_scope:
            parent_id = version.supersedes_id
            if parent_id:
                parent = by_id.get(parent_id)
                if (parent is None or parent.scope != version.scope
                    or parent.status not in {"approved", "revoked"}
                    or (parent.min_quantity, parent.max_quantity) != (version.min_quantity, version.max_quantity)
                    or parent.revision >= version.revision or parent.valid_from > version.valid_from):
                    return self._review(meta, "INVALID_SUPERSESSION", trace_id)
                replaced.add(parent_id)
        heads = [p for p in selected_scope if p.price_id not in replaced]
        latest_key = max((p.valid_from, p.revision) for p in heads)
        latest = [p for p in heads if (p.valid_from, p.revision) == latest_key]
        if len(latest) != 1:
            return self._review(meta, "AMBIGUOUS_PRICE_VERSION", trace_id)
        price = latest[0]
        # 必须先选最新已发布版本，再检查有效性，避免旧价成为隐式降级路径。
        if price.status == "revoked":
            return self._review(meta, "LATEST_PRICE_REVOKED", trace_id)
        if price.valid_until is not None and today >= price.valid_until:
            return self._review(meta, "LATEST_PRICE_EXPIRED", trace_id)
        if policy.minimum_year is not None and price.issued_on.year < policy.minimum_year:
            return self._review(meta, "PRICE_BEFORE_YEAR_POLICY", trace_id)
        if policy.review_after_days is not None and (today - price.approved_on).days >= policy.review_after_days:
            return self._review(meta, "PRICE_REVIEW_OVERDUE", trace_id)
        current = {
            "priceId": price.price_id, "revision": price.revision, "amount": format(price.amount, "f"),
            "currency": price.scope.currency, "unit": price.scope.unit,
            "productId": price.scope.product_id, "specification": price.scope.specification,
            "tradeTerm": price.scope.trade_term, "customerId": price.scope.customer_id,
            "minQuantity": format(price.min_quantity, "f"),
            "maxQuantityExclusive": format(price.max_quantity, "f") if price.max_quantity is not None else None,
            "validFrom": price.valid_from.isoformat(),
            "validUntilExclusive": price.valid_until.isoformat() if price.valid_until else None,
            "sourceRef": price.source_ref,
        }
        return result({**meta, "state": "OK", "canQuote": True, "currentPrice": current}, trace_id)

    @staticmethod
    def _matches(price: PriceVersion, request: PriceScope, quantity: Decimal) -> bool:
        """所有价格维度精确匹配；客户专价只对明确选定的同一客户可见。"""
        return (
            replace(price.scope, customer_id=None) == replace(request, customer_id=None)
            and price.scope.customer_id in {None, request.customer_id}
            and price.min_quantity <= quantity
            and (price.max_quantity is None or quantity < price.max_quantity)
        )

    @staticmethod
    def _review(meta: dict, reason: str, trace_id: str, history: bool = False) -> dict:
        """返回拒用原因而非旧金额；前端可显示历史入口但不能将其当作当前价。"""
        return result({**meta, "state": "REVIEW_REQUIRED", "reason": reason,
                       "historyAvailable": meta.get("historyAvailable", history)}, trace_id)
