"""独立合成业务示例：不会读取客户文件，也不是面向用户的生产服务。"""

import argparse
import json
import logging
import uuid
from datetime import date
from decimal import Decimal

from .contracts import DomainError, Principal, Role
from .customers import Customer, CustomerTools
from .deepseek import create_model_planner
from .dispatcher import ToolDispatcher
from .pricing import PriceScope, PriceVersion, PricingPolicy, PricingTools
from .query_service import QueryService

SAMPLE_QUESTIONS = {
    "tier": "How many tier A customers do I have?",
    "search": "Find customers with company Sample in the name.",
    "price": "Get the current price for product SAMPLE-01, specification oil, currency USD, unit kg, trade term EXW, quantity 10.",
}


def sample_service(planner):
    """固定样例仅用于演示隔离和价格时效，任何记录和金额都不是业务数据。"""
    customers = [Customer("sample-1", "sample-org", "sample-sales", company="Sample Co", tier="A"),
                 Customer("sample-2", "sample-org", "another-sales", company="Sample Other", tier="A"),
                 Customer("sample-3", "different-org", "sample-sales", company="Outside Org", tier="A")]
    scope = PriceScope("SAMPLE-01", "oil", "USD", "kg", "EXW")
    prices = [
        PriceVersion("sample-april", "sample-org", scope, 1, Decimal("12.00"), Decimal("1"), None,
                     date(2026, 4, 1), date(2026, 4, 1), None, "approved", date(2026, 4, 1), "synthetic-april"),
        PriceVersion("sample-july", "sample-org", scope, 2, Decimal("15.00"), Decimal("1"), None,
                     date(2026, 7, 1), date(2026, 7, 1), None, "approved", date(2026, 7, 1), "synthetic-july",
                     supersedes_id="sample-april"),
    ]
    reader = lambda: customers
    pricing = PricingTools(lambda: prices, reader, lambda: PricingPolicy("sample-org"),
                           clock=lambda: date(2026, 7, 15))
    return QueryService(planner, ToolDispatcher(CustomerTools(reader), pricing))


def main() -> int:
    parser = argparse.ArgumentParser(description="DeepSeek 合成业务演示，不读取实际客户数据")
    parser.add_argument("--sample", choices=SAMPLE_QUESTIONS, default="tier")
    parser.add_argument("--role", choices=["sales", "manager"], default="sales")
    parser.add_argument("--live", action="store_true", help="明确同意调用在线模型并产生一次费用")
    args = parser.parse_args()
    if not args.live:
        print(json.dumps({"code": "LIVE_CALL_NOT_CONFIRMED", "message": "Add --live to send a synthetic example."}))
        return 2
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        service = sample_service(create_model_planner())
        principal = Principal("sample-sales", "sample-org", Role(args.role))
        result = service.ask(SAMPLE_QUESTIONS[args.sample], principal, uuid.uuid4().hex)
        print(json.dumps({"synthetic": True, "sample": args.sample, "role": args.role,
                          "result": result}, ensure_ascii=False))
        return 0
    except DomainError as exc:
        print(json.dumps({"synthetic": True, "code": exc.code, "message": exc.message}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())