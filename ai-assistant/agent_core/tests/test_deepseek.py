"""离线 DeepSeek 协议及权限测试：所有网络请求使用 mock，数据完全合成。"""

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_core.contracts import DomainError, Principal, Role
from agent_core.customers import Customer, CustomerTools
from agent_core.deepseek import (
    MAX_RESPONSE_BYTES, DeepSeekConfig, DeepSeekPlanner, _NoRedirect,
    create_model_planner, validate_tool_call,
)
from agent_core.dispatcher import ToolDispatcher
from agent_core.model_port import ToolCall
from agent_core.query_service import QueryService
from agent_core.deepseek_smoke import main as smoke_main


def completion(name="count_customers", args=None, *, finish="tool_calls"):
    return {"choices": [{"finish_reason": finish, "message": {"role": "assistant", "content": None,
            "tool_calls": [{"id": "synthetic", "type": "function", "function": {
                "name": name, "arguments": json.dumps({"tier": "A"} if args is None else args)}}]}}]}


class DeepSeekTests(unittest.TestCase):
    def setUp(self):
        self.config = DeepSeekConfig("synthetic-key-for-offline-tests")
        self.planner = DeepSeekPlanner(self.config)
        self.opener = Mock()
        self.planner._opener = self.opener

    def respond(self, body):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = (
            body if isinstance(body, bytes) else json.dumps(body).encode("utf-8"))
        self.opener.open.return_value = response

    def assert_error(self, code, action):
        with self.assertRaises(DomainError) as caught:
            action()
        self.assertEqual(code, caught.exception.code)
        return caught.exception

    def plan(self):
        return self.planner.plan("How many tier A customers?", trace_id="synthetic-trace")

    def test_request_and_tool_contract(self):
        self.respond(completion())
        self.assertEqual(ToolCall("count_customers", {"tier": "A"}), self.plan())
        request = self.opener.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual("https://api.deepseek.com/chat/completions", request.full_url)
        self.assertEqual("Bearer " + self.config.api_key, request.get_header("Authorization"))
        self.assertEqual(30, self.opener.open.call_args.kwargs["timeout"])
        self.assertEqual("deepseek-flash", payload["model"])
        self.assertEqual(1024, payload["max_tokens"])
        self.assertFalse(payload["stream"])
        self.assertEqual({"type": "disabled"}, payload["thinking"])
        self.assertEqual({"count_customers", "search_customers", "get_customer_detail", "get_current_price"},
                         {t["function"]["name"] for t in payload["tools"]})
        self.opener.open.assert_called_once()

    def test_factory_uses_env_and_config_has_no_secret_repr(self):
        planner = create_model_planner({"DEEPSEEK_API_KEY": self.config.api_key, "DEEPSEEK_MODEL": "deepseek-v4-pro",
                                        "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1/"})
        self.assertEqual("deepseek-v4-pro", planner.config.model)
        self.assertEqual("https://api.deepseek.com/v1", planner.config.base_url)
        self.assertNotIn(self.config.api_key, repr(planner.config))

    def test_no_key_no_silent_mock_fallback(self):
        self.assert_error("MODEL_NOT_CONFIGURED", lambda: create_model_planner({}))

    def test_bad_env_and_config_rejected(self):
        for extra in ({"CMR_LLM_PROVIDER": "qwen"}, {"DEEPSEEK_TIMEOUT_SECONDS": "nan"},
                      {"DEEPSEEK_TIMEOUT_SECONDS": "infinity"}, {"DEEPSEEK_MAX_TOKENS": "oops"},
                      {"DEEPSEEK_MAX_TOKENS": "100000"}, {"DEEPSEEK_BASE_URL": "http://api.deepseek.com"},
                      {"DEEPSEEK_BASE_URL": "https://example.invalid"}, {"DEEPSEEK_MODEL": "bad\nmodel"},
                      {"DEEPSEEK_API_KEY": "masked-credential**"}, {"DEEPSEEK_API_KEY": "bad\r\nheader"}):
            with self.subTest(extra=list(extra)):
                self.assert_error("MODEL_CONFIG_INVALID", lambda: create_model_planner(
                    {"DEEPSEEK_API_KEY": self.config.api_key, **extra}))

    def test_redirect_handler_never_forwards(self):
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, None, None, "https://example.invalid"))

    def test_question_and_trace_limits_prevent_network(self):
        for question in ("", " ", None, "x" * 4001, "bad\x00question"):
            self.assert_error("INVALID_ARGUMENT", lambda: self.planner.plan(question))
        self.assert_error("INVALID_ARGUMENT", lambda: self.planner.plan("count", trace_id="injected\nlog"))
        self.opener.open.assert_not_called()

    def test_no_tool_means_clarification_not_free_text_answer(self):
        self.respond({"choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": "Invented count: 999"}}]})
        self.assert_error("MODEL_NEEDS_CLARIFICATION", self.plan)

    def test_truncation_is_explicit(self):
        self.respond(completion(finish="length"))
        self.assert_error("MODEL_OUTPUT_TRUNCATED", self.plan)

    def test_upstream_failed_generation_is_not_clarification(self):
        self.respond({"choices": [{"finish_reason": "content_filter", "message": {
            "role": "assistant", "content": None}}]})
        self.assert_error("MODEL_INVALID_RESPONSE", self.plan)

    def test_smoke_command_uses_only_fixed_synthetic_question(self):
        with patch("agent_core.deepseek_smoke.create_model_planner", return_value=self.planner), \
                patch("sys.stdout", new_callable=io.StringIO) as output:
            self.respond(completion())
            self.assertEqual(0, smoke_main())
        body = json.loads(self.opener.open.call_args.args[0].data)
        self.assertEqual("Count all tier A customers.", body["messages"][1]["content"])
        self.assertNotIn(self.config.api_key, output.getvalue())

    def test_smoke_command_missing_key_is_explicit(self):
        with patch("agent_core.deepseek_smoke.create_model_planner", side_effect=DomainError(
                "MODEL_NOT_CONFIGURED", "missing environment", 503)), \
                patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(1, smoke_main())
        self.assertEqual("MODEL_NOT_CONFIGURED", json.loads(output.getvalue())["code"])

    def test_multiple_calls_are_rejected(self):
        body = completion()
        body["choices"][0]["message"]["tool_calls"] *= 2
        self.respond(body)
        self.assert_error("MODEL_INVALID_RESPONSE", self.plan)

    def test_unknown_tools_and_identity_sql_are_rejected(self):
        for name, args in (("execute_sql", {"sql": "SELECT 1"}),
                           ("count_customers", {"role": "manager"}),
                           ("count_customers", {"tenantId": "other"}),
                           ("count_customers", {"ownerId": "other"}),
                           ("get_current_price", {"asOf": "2026-07-01"})):
            with self.subTest(tool=name):
                self.respond(completion(name, args))
                self.assert_error("MODEL_INVALID_RESPONSE", self.plan)

    def test_argument_types_and_bounds(self):
        for name, args in (("search_customers", {"size": True}), ("search_customers", {"size": 51}),
                           ("search_customers", {"page": 0}), ("count_customers", {"tier": "S"}),
                           ("search_customers", {"keyword": "x" * 161}),
                           ("get_customer_detail", {}), ("get_customer_detail", {"clientId": None}),
                           ("get_customer_detail", {"clientId": ""}), ("count_customers", [])):
            with self.subTest(tool=name, args=args):
                self.respond(completion(name, args))
                self.assert_error("MODEL_INVALID_RESPONSE", self.plan)

    def test_price_dimensions_and_decimal_string(self):
        args = {"productId": "synthetic-product", "specification": "oil", "currency": "USD",
                "unit": "kg", "tradeTerm": "EXW", "quantity": "10.5"}
        validate_tool_call(ToolCall("get_current_price", args))
        for overrides in ({"quantity": 10.5}, {"quantity": "1e10"}):
            self.assert_error("MODEL_INVALID_RESPONSE", lambda: validate_tool_call(
                ToolCall("get_current_price", {**args, **overrides})))

    def test_json_duplicate_keys_and_malformed_envelopes(self):
        bad_argument = completion()
        bad_argument["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = '{"tier":"A","tier":"B"}'
        for body in (b"bad-json", b"\xff", b'NaN', {}, {"choices": []}, {"choices": [None]},
                     {"choices": [None, None]}, bad_argument, b'{"choices":[],"choices":[]}'):
            with self.subTest(body_type=type(body).__name__):
                self.respond(body)
                self.assert_error("MODEL_INVALID_RESPONSE", self.plan)

    def test_response_size_is_bounded(self):
        self.respond(b" " * (MAX_RESPONSE_BYTES + 1))
        self.assert_error("MODEL_INVALID_RESPONSE", self.plan)
        self.opener.open.return_value.__enter__.return_value.read.assert_called_once_with(MAX_RESPONSE_BYTES + 1)

    def test_http_errors_are_safe_and_never_retried(self):
        for status, code in ((401, "MODEL_AUTH_FAILED"), (403, "MODEL_AUTH_FAILED"),
                             (402, "MODEL_BALANCE_INSUFFICIENT"), (429, "MODEL_RATE_LIMITED"),
                             (500, "MODEL_UNAVAILABLE"), (302, "MODEL_UNAVAILABLE"), (504, "MODEL_TIMEOUT")):
            with self.subTest(status=status):
                self.opener.open.reset_mock()
                self.opener.open.side_effect = HTTPError("https://api.deepseek.com", status,
                    self.config.api_key, {}, io.BytesIO(b"private-error-body"))
                with self.assertLogs("agent_core.deepseek", level="INFO") as logs:
                    error = self.assert_error(code, self.plan)
                self.assertNotIn(self.config.api_key, str(error))
                self.assertNotIn(self.config.api_key, " ".join(logs.output))
                self.assertNotIn("private-error-body", " ".join(logs.output))
                self.opener.open.assert_called_once()

    def test_timeouts_network_errors(self):
        for failure, code in ((TimeoutError("private"), "MODEL_TIMEOUT"),
                              (URLError(TimeoutError("private")), "MODEL_TIMEOUT"),
                              (URLError("private"), "MODEL_NETWORK_ERROR"), (OSError("private"), "MODEL_NETWORK_ERROR")):
            self.opener.open.side_effect = failure
            self.assert_error(code, self.plan)

    def test_logs_contain_trace_not_question_or_secret(self):
        self.respond(completion())
        with self.assertLogs("agent_core.deepseek", level="INFO") as logs:
            self.planner.plan("private-synthetic-question", trace_id="synthetic-trace")
        joined = " ".join(logs.output)
        self.assertIn("traceId=synthetic-trace", joined)
        self.assertIn("costMs=", joined)
        self.assertNotIn("private-synthetic-question", joined)
        self.assertNotIn(self.config.api_key, joined)

    def test_service_executes_once_and_only_returns_authorized_facts(self):
        records = [Customer("visible", "org", "seller", tier="A"),
                   Customer("private", "org", "other", tier="A"),
                   Customer("foreign", "other-org", "seller", tier="A")]
        service = QueryService(self.planner, ToolDispatcher(CustomerTools(lambda: records), Mock()))
        self.respond(completion())
        answer = service.ask("count tier A", Principal("seller", "org", Role.SALES), "synthetic-trace")
        self.assertEqual(1, answer["data"]["count"])
        self.assertEqual("synthetic-trace", answer["traceId"])
        self.opener.open.assert_called_once()
        self.assertNotIn("visible", self.opener.open.call_args.args[0].data.decode())

    def test_invalid_identity_does_not_call_model(self):
        service = QueryService(self.planner, Mock())
        self.assert_error("INVALID_PRINCIPAL", lambda: service.ask("count", None, "synthetic-trace"))
        self.opener.open.assert_not_called()

    def test_unknown_plan_does_not_touch_repository(self):
        dispatcher = Mock()
        planner = Mock()
        planner.plan.return_value = ToolCall("count_customers", {"role": "manager"})
        service = QueryService(planner, dispatcher)
        self.assert_error("MODEL_INVALID_RESPONSE", lambda: service.ask("count", Principal("seller", "org", Role.SALES), "trace"))
        dispatcher.execute.assert_not_called()

    def test_model_cannot_read_another_salespersons_detail(self):
        reader = Mock(return_value=[Customer("private", "org", "other", address="synthetic-secret")])
        service = QueryService(self.planner, ToolDispatcher(CustomerTools(reader), Mock()))
        self.respond(completion("get_customer_detail", {"clientId": "private"}))
        self.assert_error("CUSTOMER_NOT_FOUND", lambda: service.ask(
            "get private", Principal("seller", "org", Role.SALES), "synthetic-trace"))

    def test_repository_failure_is_not_zero(self):
        reader = Mock(side_effect=OSError("synthetic-storage-failure"))
        service = QueryService(self.planner, ToolDispatcher(CustomerTools(reader), Mock()))
        self.respond(completion())
        with self.assertRaises(OSError):
            service.ask("count", Principal("seller", "org", Role.SALES), "synthetic-trace")


if __name__ == "__main__":
    unittest.main()
