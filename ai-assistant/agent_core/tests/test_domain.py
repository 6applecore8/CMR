"""领域规则反例测试；仅构造合成数据，不访问真实客户、Wiki 或模型。"""

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_core.contracts import DomainError, Principal, Role
from agent_core.customers import Customer, CustomerTools
from agent_core.dispatcher import ToolDispatcher
from agent_core.model_port import ToolCall, UnconfiguredModel
from agent_core.pricing import PriceScope, PriceVersion, PricingPolicy, PricingTools, change_policy


SALES = Principal("staff-a", "org-a", Role.SALES)
MANAGER = Principal("manager-a", "org-a", Role.MANAGER)
TODAY = date(2026, 10, 26)
NOW = datetime(2026, 10, 26, 10, tzinfo=timezone.utc)


def clients():
    return [
        Customer("c1", "org-a", "staff-a", "Synthetic One", "Same", "A", "email", "synthetic-address", "synthetic-need"),
        Customer("c2", "org-a", "staff-a", "Synthetic Two", "Same", "B", "alibaba"),
        Customer("c3", "org-a", "staff-b", "Other Owner", "Same", "A"),
        Customer("c4", "org-b", "staff-a", "Other Organization", "Other", "A"),
        Customer("c5", "org-a", None, "Unassigned", "Unassigned", "A"),
        Customer("c6", "org-a", "staff-a", "Deleted", "Deleted", "A", deleted=True),
    ]


def price(price_id="april", **overrides):
    fields = dict(
        price_id=price_id, tenant_id="org-a",
        scope=PriceScope("SYNTH-P-001", "standard", "USD", "kg", "EXW"),
        revision=1, amount=Decimal("100.00"), min_quantity=Decimal("1"), max_quantity=None,
        issued_on=date(2026, 4, 1), valid_from=date(2026, 4, 1), valid_until=None,
        status="approved", approved_on=date(2026, 4, 1), source_ref="synthetic/price-april",
    )
    return PriceVersion(**(fields | overrides))


def july(**overrides):
    return price("july", **(dict(
        revision=2, amount=Decimal("120.00"), issued_on=date(2026, 7, 1),
        valid_from=date(2026, 7, 1), approved_on=date(2026, 7, 1),
        supersedes_id="april", source_ref="synthetic/price-july",
    ) | overrides))


def query(**overrides):
    return dict(productId="SYNTH-P-001", specification="standard", currency="USD",
                unit="kg", tradeTerm="EXW", quantity="10") | overrides


def pricing(versions, policy=None, today=TODAY):
    return PricingTools(lambda: versions, clients, lambda: policy or PricingPolicy("org-a"), lambda: today)


class CustomerToolTests(unittest.TestCase):
    def setUp(self):
        self.tools = CustomerTools(clients, lambda: NOW)

    def run_tool(self, tool="count_customers", args=None, principal=SALES):
        return self.tools.execute(tool, args or {}, principal, "synthetic-trace")["data"]

    def test_sales_count_only_owned_non_deleted_customers(self):
        self.assertEqual(self.run_tool()["count"], 2)
        self.assertEqual(self.run_tool(args={"tier": "A"})["count"], 1)

    def test_manager_count_still_excludes_other_organization(self):
        self.assertEqual(self.run_tool(principal=MANAGER)["count"], 4)
        self.assertEqual(self.run_tool(args={"tier": "A"}, principal=MANAGER)["count"], 3)

    def test_channel_filter_uses_same_authorization_scope(self):
        self.assertEqual(self.run_tool(args={"channel": "alibaba"})["count"], 1)

    def test_search_is_paginated_and_ambiguous_name_requires_selection(self):
        data = self.run_tool("search_customers", {"keyword": "Same", "size": 1})
        self.assertEqual(data["total"], 2)
        self.assertEqual(len(data["items"]), 1)
        self.assertTrue(data["requiresSelection"])
        self.assertNotIn("address", data["items"][0])
        self.assertNotIn("requirement", data["items"][0])

    def test_detail_returns_known_missing_fields_as_null(self):
        data = self.run_tool("get_customer_detail", {"clientId": "c2"})
        self.assertIsNone(data["customer"]["address"])
        self.assertIsNone(data["customer"]["requirement"])

    def test_detail_keeps_authorized_facts_without_raw_markdown(self):
        data = self.run_tool("get_customer_detail", {"clientId": "c1"})
        self.assertEqual(data["customer"]["address"], "synthetic-address")
        self.assertNotIn("raw_markdown", data["customer"])

    def test_forbidden_and_missing_customer_have_same_error(self):
        errors = []
        for client_id in ("c3", "c4", "c5", "c6", "missing"):
            with self.assertRaises(DomainError) as caught:
                self.run_tool("get_customer_detail", {"clientId": client_id})
            errors.append((caught.exception.code, caught.exception.status, str(caught.exception)))
        self.assertEqual(len(set(errors)), 1)

    def test_unknown_or_privilege_parameters_are_rejected(self):
        for name in ("sql", "role", "tenantId", "ownerId", "asOf"):
            with self.subTest(name=name), self.assertRaises(DomainError):
                self.run_tool(args={name: "injected"})

    def test_invalid_filters_and_pagination_are_rejected(self):
        for args in ({"tier": "admin"}, {"channel": "all;DROP"}, {"size": 51},
                     {"page": True}, {"page": 0}, {"keyword": {"$ne": ""}}, {"keyword": "x\n"}):
            with self.subTest(args=args), self.assertRaises(DomainError):
                self.run_tool("search_customers", args)

    def test_query_failure_is_not_reported_as_zero(self):
        def unavailable():
            raise OSError("synthetic storage failure")
        with self.assertRaises(OSError):
            CustomerTools(unavailable).execute("count_customers", {}, SALES, "trace")

    def test_duplicate_ids_fail_closed_instead_of_double_counting(self):
        with self.assertRaises(DomainError) as caught:
            CustomerTools(lambda: [clients()[0], clients()[0]]).execute("count_customers", {}, SALES, "trace")
        self.assertEqual(caught.exception.code, "SOURCE_INCONSISTENT")

    def test_result_has_trace_and_server_timestamp(self):
        response = self.tools.execute("count_customers", {}, SALES, "trace-123")
        self.assertEqual(response["traceId"], "trace-123")
        self.assertEqual(response["data"]["asOf"], NOW.isoformat())

    def test_other_organization_duplicates_do_not_change_local_count(self):
        rows = clients() + [clients()[3]]
        response = CustomerTools(lambda: rows).execute("count_customers", {}, SALES, "trace")
        self.assertEqual(response["data"]["count"], 2)

    def test_customer_source_types_fail_before_querying(self):
        for changes in ({"deleted": "false"}, {"tier": "X"}, {"owner_id": " staff-a "}, {"requirement": []}):
            with self.subTest(changes=changes), self.assertRaises(DomainError):
                replace(clients()[0], **changes)


class PolicyTests(unittest.TestCase):
    def test_sales_cannot_change_policy(self):
        with self.assertRaises(DomainError) as caught:
            change_policy(SALES, PricingPolicy("org-a"), {"minimum_year": None}, 1)
        self.assertEqual(caught.exception.status, 403)

    def test_manager_cannot_change_other_organization_policy(self):
        with self.assertRaises(DomainError):
            change_policy(MANAGER, PricingPolicy("org-b"), {"minimum_year": 2027}, 1)

    def test_change_creates_new_snapshot_without_mutating_old(self):
        old = PricingPolicy("org-a")
        new = change_policy(MANAGER, old, {"minimum_year": 2027, "review_after_days": 90}, 1)
        self.assertEqual((old.minimum_year, old.version), (2026, 1))
        self.assertEqual((new.minimum_year, new.version), (2027, 2))

    def test_policy_version_conflict_is_409(self):
        with self.assertRaises(DomainError) as caught:
            change_policy(MANAGER, PricingPolicy("org-a", version=2), {"minimum_year": 2027}, 1)
        self.assertEqual(caught.exception.status, 409)

    def test_policy_cannot_relax_approval_or_set_identity(self):
        for field in ("require_approval", "tenant_id", "role", "version"):
            with self.subTest(field=field), self.assertRaises(DomainError):
                change_policy(MANAGER, PricingPolicy("org-a"), {field: False}, 1)

    def test_policy_types_and_boundaries_are_strict(self):
        for fields in ({"minimum_year": True}, {"minimum_year": "2026"}, {"review_after_days": 0},
                       {"review_after_days": True}, {"allow_history": "false"}):
            with self.subTest(fields=fields), self.assertRaises(DomainError):
                change_policy(MANAGER, PricingPolicy("org-a"), fields, 1)

    def test_invalid_principal_cannot_claim_role_with_string(self):
        for values in (("u", "org-a", "manager"), ([], "org-a", Role.SALES), ("", "org-a", Role.SALES)):
            with self.subTest(values=values), self.assertRaises(DomainError):
                Principal(*values)


class PricingTests(unittest.TestCase):
    def response(self, versions, args=None, policy=None, today=TODAY, principal=SALES):
        return pricing(versions, policy, today).execute(args or query(), principal, "trace")["data"]

    def assert_review(self, data, reason):
        self.assertEqual(data["state"], "REVIEW_REQUIRED")
        self.assertEqual(data["reason"], reason)
        self.assertFalse(data["canQuote"])
        self.assertIsNone(data["currentPrice"])
        self.assertNotIn("amount", data)

    def test_july_replaces_april_for_identical_conditions(self):
        data = self.response([price(), july()])
        self.assertEqual(data["currentPrice"]["priceId"], "july")
        self.assertEqual(data["currentPrice"]["amount"], "120.00")
        self.assertEqual(data["policyVersion"], 1)

    def test_future_version_does_not_replace_current(self):
        data = self.response([price(), july()], today=date(2026, 6, 1))
        self.assertEqual(data["currentPrice"]["priceId"], "april")

    def test_unapproved_draft_does_not_replace_current(self):
        data = self.response([price(), july(status="draft", approved_on=None)])
        self.assertEqual(data["currentPrice"]["priceId"], "april")

    def test_future_approval_does_not_replace_current(self):
        data = self.response([price(), july(approved_on=date(2026, 11, 1))])
        self.assertEqual(data["currentPrice"]["priceId"], "april")

    def test_expired_latest_never_falls_back_to_april(self):
        self.assert_review(self.response([price(), july(valid_until=date(2026, 8, 1))]), "LATEST_PRICE_EXPIRED")

    def test_revoked_latest_never_falls_back_to_april(self):
        self.assert_review(self.response([price(), july(status="revoked")]), "LATEST_PRICE_REVOKED")

    def test_expiry_boundary_is_exclusive(self):
        self.assert_review(self.response([price(valid_until=TODAY)]), "LATEST_PRICE_EXPIRED")

    def test_old_year_is_blocked_and_threshold_is_configurable(self):
        old = price(issued_on=date(2025, 12, 1), valid_from=date(2025, 12, 1), approved_on=date(2025, 12, 1))
        self.assert_review(self.response([old]), "PRICE_BEFORE_YEAR_POLICY")
        self.assertTrue(self.response([old], policy=PricingPolicy("org-a", minimum_year=None))["canQuote"])

    def test_new_review_is_a_new_version_not_a_mutation(self):
        old = price(issued_on=date(2025, 12, 1), valid_from=date(2025, 12, 1), approved_on=date(2025, 12, 1))
        data = self.response([old, july()])
        self.assertTrue(data["canQuote"])
        self.assertEqual(old.issued_on.year, 2025)

    def test_review_period_is_enforced(self):
        self.assert_review(self.response([price()], policy=PricingPolicy("org-a", review_after_days=90)), "PRICE_REVIEW_OVERDUE")

    def test_wrong_dimensions_do_not_return_price(self):
        for changes in ({"currency": "EUR"}, {"specification": "other"}, {"unit": "g"},
                        {"tradeTerm": "FOB"}, {"productId": "OTHER"}):
            with self.subTest(changes=changes):
                self.assert_review(self.response([price()], args=query(**changes)), "NO_PUBLISHED_PRICE")

    def test_other_organization_is_not_visible_even_to_manager(self):
        self.assert_review(self.response([price(tenant_id="org-b")], principal=MANAGER), "NO_PUBLISHED_PRICE")

    def test_customer_specific_price_requires_customer_access(self):
        with self.assertRaises(DomainError) as caught:
            self.response([price()], args=query(customerId="c3"))
        self.assertEqual(caught.exception.status, 404)

    def test_specific_price_is_used_only_for_selected_customer(self):
        specific = price("special", scope=replace(price().scope, customer_id="c1"), amount=Decimal("90.00"))
        self.assertEqual(self.response([price(), specific], args=query(customerId="c1"))["currentPrice"]["priceId"], "special")
        self.assertEqual(self.response([price(), specific])["currentPrice"]["priceId"], "april")

    def test_expired_specific_price_does_not_silently_use_generic_price(self):
        special = price("special", scope=replace(price().scope, customer_id="c1"), valid_until=date(2026, 5, 1))
        self.assert_review(self.response([price(), special], args=query(customerId="c1")), "LATEST_PRICE_EXPIRED")

    def test_quantity_boundary_and_overlap_are_not_guessed(self):
        low = price(max_quantity=Decimal("10"))
        high = price("high", min_quantity=Decimal("10"), amount=Decimal("80.00"))
        self.assertEqual(self.response([low, high])["currentPrice"]["priceId"], "high")
        overlap = price("overlap", min_quantity=Decimal("5"), max_quantity=Decimal("20"))
        self.assert_review(self.response([price(), overlap]), "OVERLAPPING_QUANTITY_BANDS")

    def test_same_rank_versions_require_review(self):
        self.assert_review(self.response([price(), price("duplicate-rank")]), "AMBIGUOUS_PRICE_VERSION")

    def test_duplicate_identifiers_require_review(self):
        self.assert_review(self.response([price(), price()]), "DUPLICATE_PRICE_ID")

    def test_invalid_supersession_requires_review(self):
        self.assert_review(self.response([price(), july(supersedes_id="missing")]), "INVALID_SUPERSESSION")

    def test_hidden_history_never_discloses_old_amount(self):
        data = self.response([price(valid_until=date(2026, 8, 1))], policy=PricingPolicy("org-a", allow_history=False))
        self.assertFalse(data["historyAvailable"])
        self.assertNotIn("100.00", str(data))

    def test_malicious_tool_parameters_are_rejected(self):
        for changes in ({"asOf": "2025-01-01"}, {"sql": "SELECT *"}, {"role": "manager"},
                        {"quantity": 10.1}, {"quantity": "NaN"}, {"quantity": "0"}, {"quantity": "1e10"}):
            with self.subTest(changes=changes), self.assertRaises(DomainError):
                self.response([price()], args=query(**changes))

    def test_missing_required_conditions_are_not_assumed(self):
        args = query()
        args.pop("currency")
        with self.assertRaises(DomainError):
            self.response([price()], args=args)

    def test_price_records_validate_source_dates_and_exact_amount(self):
        for changes in ({"amount": 1.1}, {"amount": Decimal("NaN")}, {"source_ref": ""},
                        {"valid_until": date(2026, 4, 1)}, {"approved_on": None}, {"revision": True}):
            with self.subTest(changes=changes), self.assertRaises(DomainError):
                price(**changes)

    def test_repository_failure_is_not_a_business_empty_state(self):
        def unavailable():
            raise OSError("synthetic storage failure")
        service = PricingTools(unavailable, clients, lambda: PricingPolicy("org-a"), lambda: TODAY)
        with self.assertRaises(OSError):
            service.execute(query(), SALES, "trace")

    def test_only_drafts_or_future_prices_are_not_advertised_as_history(self):
        rows = [july(status="draft", approved_on=None)]
        data = self.response(rows)
        self.assertFalse(data["historyAvailable"])
        data = self.response([july()], today=date(2026, 6, 1))
        self.assertFalse(data["historyAvailable"])

    def test_approved_version_cannot_supersede_unpublished_draft(self):
        draft = price(status="draft", approved_on=None)
        self.assert_review(self.response([draft, july()]), "INVALID_SUPERSESSION")

    def test_policy_from_another_organization_is_not_used(self):
        with self.assertRaises(DomainError):
            self.response([price()], policy=PricingPolicy("org-b"))

    def test_supersession_cannot_cross_customer_scope(self):
        foreign_scope = price(scope=replace(price().scope, customer_id="c3"))
        self.assert_review(self.response([foreign_scope, july()]), "INVALID_SUPERSESSION")


class DispatcherTests(unittest.TestCase):
    def setUp(self):
        self.dispatcher = ToolDispatcher(CustomerTools(clients), pricing([price()]))

    def test_supported_read_tool_works(self):
        response = self.dispatcher.execute(ToolCall("count_customers", {"tier": "A"}), SALES, "trace")
        self.assertEqual(response["data"]["count"], 1)

    def test_sql_and_mutations_are_not_registered(self):
        for name in ("execute_sql", "change_policy", "update_customer", "send_email"):
            with self.subTest(name=name), self.assertRaises(DomainError):
                self.dispatcher.execute(ToolCall(name, {}), MANAGER, "trace")

    def test_model_is_explicitly_unconfigured(self):
        with self.assertRaises(DomainError) as caught:
            UnconfiguredModel().plan("synthetic question")
        self.assertEqual(caught.exception.code, "MODEL_NOT_CONFIGURED")


if __name__ == "__main__":
    unittest.main()
