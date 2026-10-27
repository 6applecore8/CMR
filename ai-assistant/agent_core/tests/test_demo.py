"""合成演示端到端测试：模型与数据均为可控样例，不调用云端。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent_core.contracts import Principal, Role
from agent_core.demo import sample_service
from agent_core.model_port import ToolCall


class FixedPlanner:
    def __init__(self, call):
        self.call = call
    def plan(self, question, *, trace_id=None):
        return self.call


class DemoTests(unittest.TestCase):
    def test_sales_and_manager_count_differ(self):
        service = sample_service(FixedPlanner(ToolCall("count_customers", {"tier": "A"})))
        self.assertEqual(1, service.ask("synthetic", Principal("sample-sales", "sample-org", Role.SALES), "trace")["data"]["count"])
        self.assertEqual(2, service.ask("synthetic", Principal("manager", "sample-org", Role.MANAGER), "trace")["data"]["count"])

    def test_latest_approved_price_wins(self):
        args = {"productId":"SAMPLE-01", "specification":"oil", "currency":"USD", "unit":"kg", "tradeTerm":"EXW", "quantity":"10"}
        service = sample_service(FixedPlanner(ToolCall("get_current_price", args)))
        data = service.ask("synthetic", Principal("sample-sales", "sample-org", Role.SALES), "trace")["data"]
        self.assertTrue(data["canQuote"])
        self.assertEqual("sample-july", data["currentPrice"]["priceId"])
        self.assertEqual("15.00", data["currentPrice"]["amount"])


if __name__ == "__main__":
    unittest.main()