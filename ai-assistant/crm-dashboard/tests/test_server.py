"""CRM 看板核心逻辑测试（只使用临时目录，不触碰真实客户数据）。"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path


HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import server  # noqa: E402


class MarkdownParsingTests(unittest.TestCase):
    def test_parse_profile_supports_chinese_template_and_notes(self) -> None:
        content = """# Aroma House — Lin

## Profile

| 字段 | 值 |
|---|---|
| client_id | 2026-08-27_aroma_house |
| company | Aroma House |
| contact_name | Lin |
| country_region | Singapore |
| market_bucket | SEA |
| source | alibaba |
| icp_score | 78 |
| icp_tier | A |
| status | sampling |
| next_action | 确认寄样地址 |

## Public Summary

小型香氛品牌。

## Notes

已在 Alibaba 询盘。
"""
        result = server.parse_profile(content, "fallback")
        self.assertEqual(result["client_id"], "2026-08-27_aroma_house")
        self.assertEqual(result["market_bucket"], "SEA")
        self.assertEqual(result["source"], "alibaba")
        self.assertEqual(result["icp_score"], 78)
        self.assertEqual(result["icp_tier"], "A")
        self.assertEqual(result["status"], "sampling")
        self.assertIn("Alibaba", result["notes"])

    def test_parse_profile_supports_legacy_field_value_table(self) -> None:
        content = """# Legacy Brand

| field | value |
|------|------|
| company | Legacy Brand |
| contact | Pat |
| email | pat@example.com |
| market | EU (UK) |
| product | candle fragrance oils |
| score | 55 |
| tier | B |
| status | paid (sample freight received) |
"""
        result = server.parse_profile(content, "legacy_brand")
        self.assertEqual(result["client_id"], "legacy_brand")
        self.assertEqual(result["contact_name"], "Pat")
        self.assertEqual(result["known_email"], "pat@example.com")
        self.assertEqual(result["product_interest"], "candle fragrance oils")
        self.assertEqual(result["status"], "paid")


class MergeAndPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "clients").mkdir()
        (self.root / "leads").mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_merge_profile_index_and_pipeline(self) -> None:
        index = server.parse_index("""# 客户索引

| client_id | company | market_bucket | tier | score | status | source | updated |
|---|---|---|---|---|---|---|---|
| profile_id | Index Name | EU_US | B | 40 | researched | web_search | 2026-08-20 |
| index_only | Index Only | SEA | C | 25 | new | alibaba | 2026-08-21 |
""")
        pipeline = server.parse_pipeline("""# Lead Pipeline

## B 级跟进

| client_id | company | market | status | next_action | updated |
|---|---|---|---|---|---|
| profile_id | Pipeline Name | EU_US (UK) | replied | 等客户确认 | 2026-08-27 |
| pipeline_only | Pipeline Only | OTHER | outreach_1 | 发 Mail 1 | 2026-08-27 |
""")
        profile = server.parse_profile("""# Profile Name — Alex

## Profile

| 字段 | 值 |
|---|---|
| client_id | profile_id |
| company | Profile Name |
| contact_name | Alex |
| market_bucket | EU_US |
| status | new |
| icp_score | 65 |
| icp_tier | A |
""", "profile_id")
        merged = server.merge_records(index, pipeline, {"profile_id": profile})
        by_id = {item["client_id"]: item for item in merged}
        self.assertEqual(set(by_id), {"profile_id", "index_only", "pipeline_only"})
        self.assertEqual(by_id["profile_id"]["company"], "Profile Name")
        self.assertEqual(by_id["profile_id"]["status"], "replied")
        self.assertEqual(by_id["profile_id"]["next_action"], "等客户确认")
        self.assertEqual(by_id["index_only"]["source"], "alibaba")
        self.assertFalse(by_id["index_only"]["has_profile"])

    def test_create_alibaba_client_syncs_three_sources(self) -> None:
        (self.root / "clients" / "_index.md").write_text(
            "# 客户索引\n\n| client_id | company | market_bucket | tier | score | status | source | updated |\n|---|---|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
        (self.root / "leads" / "pipeline.md").write_text(
            "# Lead Pipeline\n\n## B 级跟进\n\n| client_id | company | market | status | next_action | updated |\n|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
        store = server.CRMStore(self.root)
        created = store.create_client(
            {
                "company": "Alibaba Aroma Co.",
                "contact_name": "Mia",
                "known_email": "mia@example.com",
                "known_phone": "+86 123456789",
                "country_region": "Guangzhou, China",
                "market_bucket": "OTHER",
                "source": "alibaba",
                "product_interest": "soap fragrance oils",
                "icp_tier": "B",
                "icp_score": 62,
                "status": "new",
                "next_action": "确认采购品类",
                "notes": "来自 Alibaba 询盘。",
            }
        )
        client_path = self.root / "clients" / f"{created['client_id']}.md"
        self.assertTrue(client_path.exists())
        self.assertIn("| source | alibaba |", client_path.read_text(encoding="utf-8"))
        self.assertIn(created["client_id"], (self.root / "clients" / "_index.md").read_text(encoding="utf-8"))
        self.assertIn(created["client_id"], (self.root / "leads" / "pipeline.md").read_text(encoding="utf-8"))
        scanned = {item["client_id"]: item for item in store.list_clients()}
        self.assertEqual(scanned[created["client_id"]]["source"], "alibaba")
        self.assertEqual(scanned[created["client_id"]]["next_action"], "确认采购品类")

    def test_channel_classification_and_empty_alibaba_client(self) -> None:
        merged = server.merge_records(
            {"ali": {"client_id": "ali", "source": "Alibaba inquiry"}, "mail": {"client_id": "mail", "source": "website"}},
            {},
            {},
        )
        by_id = {item["client_id"]: item for item in merged}
        self.assertEqual(by_id["ali"]["customer_channel"], "alibaba")
        self.assertEqual(by_id["mail"]["customer_channel"], "email")

        store = server.CRMStore(self.root)
        created = store.create_client({"channel": "alibaba"})
        self.assertEqual(created["source"], "alibaba")
        self.assertEqual(created["display_name"], "未命名阿里客户")
        self.assertIn("unnamed_alibaba", created["client_id"])
        self.assertTrue((self.root / "clients" / f"{created['client_id']}.md").exists())
        scanned = {item["client_id"]: item for item in store.list_clients()}[created["client_id"]]
        self.assertEqual(scanned["customer_channel"], "alibaba")
        self.assertEqual(scanned["display_name"], "未命名阿里客户")

    def test_address_and_product_fields_persist_on_create_and_update(self) -> None:
        store = server.CRMStore(self.root)
        created = store.create_client(
            {
                "channel": "alibaba",
                "address": "Room 18, Xiamen\nChina",
                "known_phone": "+86 13800000000",
                "product_raw": "产品: Lavender Oil\n香型: fresh lavender; 数量: 100 kg; 用途: soap",
                "notes": "原始询盘备注",
            }
        )
        profile_path = self.root / "clients" / f"{created['client_id']}.md"
        profile_text = profile_path.read_text(encoding="utf-8")
        self.assertIn("| address | Room 18, Xiamen", profile_text)
        self.assertIn("| product_raw | 产品: Lavender Oil<br>香型: fresh lavender; 数量: 100 kg; 用途: soap |", profile_text)
        scanned = {item["client_id"]: item for item in store.list_clients()}[created["client_id"]]
        self.assertEqual(scanned["address"], "Room 18, Xiamen\nChina")
        self.assertEqual(scanned["product_name"], "Lavender Oil")
        self.assertEqual(scanned["product_quantity"], "100 kg")
        self.assertIn("Lavender Oil", scanned["product_interest"])

        updated = store.update_client(created["client_id"], {"address": "Updated delivery address", "product_name": "Manual Blend"})
        self.assertEqual(updated["address"], "Updated delivery address")
        rescanned = {item["client_id"]: item for item in store.list_clients()}[created["client_id"]]
        self.assertEqual(rescanned["address"], "Updated delivery address")
        self.assertEqual(rescanned["product_name"], "Manual Blend")

        # 第二次只提交新原文时，未显式提交的自动字段应刷新；
        # product_name 模拟前端已手改字段，必须保持不变。
        updated_again = store.update_client(
            created["client_id"],
            {
                "product_raw": "Product perfume oil / Scent jasmine / Qty 25kg / Size 1kg bottle / Target USD 18/kg / Application perfume",
                "product_name": "Manual Blend",
            },
        )
        self.assertEqual(updated_again["product_name"], "Manual Blend")
        refreshed = {item["client_id"]: item for item in store.list_clients()}[created["client_id"]]
        self.assertEqual(refreshed["product_specification"], "1kg bottle")
        self.assertEqual(refreshed["target_price"], "USD 18/kg")
        self.assertEqual(refreshed["product_quantity"], "25kg")

    def test_product_parser_supports_bilingual_labels_and_heuristics(self) -> None:
        labeled = server.parse_product_info("Product: Rose Oil, Scent: fresh rose; Application: candle; Qty: 250 kg; Size: 10ml; Target price: USD 8/kg; Requirement: IFRA")
        self.assertEqual(labeled["product_name"], "Rose Oil")
        self.assertEqual(labeled["fragrance_requirement"], "fresh rose")
        self.assertEqual(labeled["product_application"], "candle")
        self.assertEqual(labeled["product_quantity"], "250 kg")
        self.assertEqual(labeled["product_specification"], "10ml")
        self.assertEqual(labeled["target_price"], "USD 8/kg")
        self.assertEqual(labeled["other_requirements"], "IFRA")
        chinese = server.parse_product_info("产品名称：茉莉香精；香型要求：清新；产品用途：香水；采购量：500 公斤；目标价：8 元")
        self.assertEqual(chinese["product_name"], "茉莉香精")
        self.assertEqual(chinese["fragrance_requirement"], "清新")
        self.assertEqual(chinese["product_application"], "香水")
        self.assertEqual(chinese["product_quantity"], "500 公斤")
        self.assertEqual(chinese["target_price"], "8 元")
        heuristic = server.parse_product_info("Lavender soap fragrance; order 200 kg for candle at $9/kg")
        self.assertEqual(heuristic["product_quantity"], "200 kg")
        self.assertEqual(heuristic["target_price"], "$9/kg")
        self.assertIn("candle", heuristic["product_application"])
        cutoff = server.parse_product_info("Size: 1kg bottle; Target: USD 18/kg; Application: perfume")
        self.assertEqual(cutoff["product_specification"], "1kg bottle")
        self.assertEqual(cutoff["target_price"], "USD 18/kg")
        self.assertEqual(cutoff["product_application"], "perfume")
        continuous = server.parse_product_info("Product perfume oil / Scent jasmine / Qty 25kg / Size 1kg bottle / Target USD 18/kg / Application perfume")
        self.assertEqual(continuous["product_name"], "perfume oil")
        self.assertEqual(continuous["fragrance_requirement"], "jasmine")
        self.assertEqual(continuous["product_quantity"], "25kg")
        self.assertEqual(continuous["product_specification"], "1kg bottle")
        self.assertEqual(continuous["target_price"], "USD 18/kg")
        self.assertEqual(continuous["product_application"], "perfume")

    def test_update_changes_only_editable_fields_and_preserves_outreach(self) -> None:
        record = {
            "client_id": "2026-08-27_update_target",
            "company": "Update Target",
            "contact_name": "Jo",
            "market_bucket": "EU_US",
            "source": "website",
            "icp_tier": "B",
            "icp_score": 50,
            "status": "new",
            "next_action": "初次联系",
            "created_at": "2026-08-27",
            "updated_at": "2026-08-27",
            "notes": "旧备注",
        }
        (self.root / "clients" / f"{record['client_id']}.md").write_text(
            server.render_client_markdown(record).replace("| | | | |", "| 2026-08-27 | email | Mail 1 | queued |"),
            encoding="utf-8",
        )
        (self.root / "clients" / "_index.md").write_text(
            "# 客户索引\n\n| client_id | company | market_bucket | tier | score | status | source | updated |\n|---|---|---|---|---|---|---|---|\n| 2026-08-27_update_target | Update Target | EU_US | B | 50 | new | website | 2026-08-27 |\n",
            encoding="utf-8",
        )
        (self.root / "leads" / "pipeline.md").write_text(
            "# Lead Pipeline\n\n## B 级跟进\n\n| client_id | company | market | status | next_action | updated |\n|---|---|---|---|---|---|\n| 2026-08-27_update_target | Update Target | EU_US | new | 初次联系 | 2026-08-27 |\n",
            encoding="utf-8",
        )
        store = server.CRMStore(self.root)
        updated = store.update_client(record["client_id"], {"status": "replied", "next_action": "周五确认样品", "notes": "客户已回复，等待地址。"})
        self.assertEqual(updated["status"], "replied")
        profile_text = (self.root / "clients" / f"{record['client_id']}.md").read_text(encoding="utf-8")
        self.assertIn("| status | replied |", profile_text)
        self.assertIn("周五确认样品", profile_text)
        self.assertIn("客户已回复，等待地址。", profile_text)
        self.assertIn("| 2026-08-27 | email | Mail 1 | queued |", profile_text)
        self.assertIn("| 2026-08-27_update_target | Update Target | EU_US | replied | 周五确认样品 |", (self.root / "leads" / "pipeline.md").read_text(encoding="utf-8"))

    def test_structured_logs_have_schema_and_redact_sensitive_values(self) -> None:
        (self.root / "clients" / "_index.md").write_text("# 客户索引\n", encoding="utf-8")
        (self.root / "leads" / "pipeline.md").write_text("# Lead Pipeline\n", encoding="utf-8")
        store = server.CRMStore(self.root)
        store.list_clients()
        with self.assertRaises(server.ValidationError):
            store.create_client({"company": "", "known_email": "private@example.com", "known_phone": "+86 13800000000", "notes": "绝密备注"})
        log_path = self.root / "crm-dashboard" / "logs" / server.LOG_FILENAME
        self.assertTrue(log_path.exists())
        entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertGreaterEqual(len(entries), 2)
        required = {"timestamp", "level", "event", "task_phase", "status", "error_code", "message", "details", "context"}
        self.assertTrue(all(required <= set(entry) for entry in entries))
        self.assertIn(server.ERROR_CODES["validation"], {entry["error_code"] for entry in entries})
        serialized = log_path.read_text(encoding="utf-8")
        self.assertNotIn("private@example.com", serialized)
        self.assertNotIn("13800000000", serialized)
        self.assertNotIn("绝密备注", serialized)


class HttpApiTests(unittest.TestCase):
    def test_health_and_clients_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "clients").mkdir()
            (root / "leads").mkdir()
            (root / "clients" / "_index.md").write_text("# 客户索引\n", encoding="utf-8")
            (root / "leads" / "pipeline.md").write_text("# Lead Pipeline\n", encoding="utf-8")
            httpd = server.create_server("127.0.0.1", 0, root)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{httpd.server_port}"
                with urllib.request.urlopen(base + "/api/health", timeout=3) as response:
                    health = json.loads(response.read().decode("utf-8"))
                with urllib.request.urlopen(base + "/api/clients", timeout=3) as response:
                    clients = json.loads(response.read().decode("utf-8"))
                self.assertEqual(health["status"], "ok")
                self.assertEqual(clients["stats"]["total"], 0)
                self.assertEqual(clients["clients"], [])
                request = urllib.request.Request(base + "/api/clients", data=b"{}", method="POST", headers={"Content-Type": "application/json"})
                with self.assertRaises(urllib.error.HTTPError) as error_context:
                    urllib.request.urlopen(request, timeout=3)
                error_body = json.loads(error_context.exception.read().decode("utf-8"))
                self.assertEqual(error_body["error_code"], server.ERROR_CODES["validation"])
                # 前端取消按钮回归保护：即使没有浏览器驱动，也能确保按钮存在并
                # 绑定到不会提交表单的 modal 关闭入口。
                index_html = (HERE / "index.html").read_text(encoding="utf-8")
                app_js = (HERE / "app.js").read_text(encoding="utf-8")
                self.assertIn('id="add-cancel"', index_html)
                self.assertIn('function closeModal(dialog)', app_js)
                self.assertIn('$("#add-cancel").addEventListener("click", () => closeModal($("#add-dialog")));', app_js)
                self.assertIn('id="channel-alibaba"', index_html)
                self.assertIn('id="channel-email"', index_html)
                self.assertIn('id="product-parser-fields"', index_html)
                self.assertIn('/api/product-info/parse', app_js)
                self.assertIn('export-alibaba-btn', index_html)
                self.assertIn('href="/api/clients/export.csv?channel=alibaba"', index_html)
                self.assertIn('download="alibaba-customers.csv"', index_html)
                self.assertNotIn("response.blob()", app_js)
                self.assertNotIn("createObjectURL", app_js)
                self.assertIn("if (!productParserState.manual.has(field)) input.value = suggestion;", app_js)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=3)

    def test_product_parse_and_alibaba_csv_api(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "clients").mkdir()
            (root / "leads").mkdir()
            (root / "clients" / "_index.md").write_text("# 客户索引\n", encoding="utf-8")
            (root / "leads" / "pipeline.md").write_text("# Lead Pipeline\n", encoding="utf-8")
            store = server.CRMStore(root)
            ali = store.create_client({"channel": "alibaba", "contact_name": "李雷", "address": "厦门", "product_raw": "产品: 茉莉香精; 数量: 20 kg", "notes": "敏感备注 secret"})
            store.create_client({"company": "Mail Brand", "source": "website"})
            httpd = server.create_server("127.0.0.1", 0, root)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{httpd.server_port}"
                parser_request = urllib.request.Request(
                    base + "/api/product-info/parse",
                    data=json.dumps({"raw_text": "Product: Rose Oil; Qty: 10 kg; Target price: USD 7/kg"}).encode("utf-8"),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(parser_request, timeout=3) as response:
                    parsed = json.loads(response.read().decode("utf-8"))
                self.assertEqual(parsed["fields"]["product_name"], "Rose Oil")
                self.assertEqual(parsed["fields"]["product_quantity"], "10 kg")
                self.assertEqual(parsed["fields"]["target_price"], "USD 7/kg")

                with urllib.request.urlopen(base + "/api/clients/export.csv?channel=alibaba", timeout=3) as response:
                    csv_bytes = response.read()
                    self.assertTrue(csv_bytes.startswith(b"\xef\xbb\xbf"))
                    csv_text = csv_bytes.decode("utf-8-sig")
                self.assertIn("ID,姓名,公司,地址,电话,邮箱,产品原文,产品名称", csv_text.splitlines()[0])
                self.assertIn(ali["client_id"], csv_text)
                self.assertIn("茉莉香精", csv_text)
                self.assertNotIn("Mail Brand", csv_text)
                log_path = root / "crm-dashboard" / "logs" / server.LOG_FILENAME
                log_text = log_path.read_text(encoding="utf-8")
                self.assertIn(server.ERROR_CODES["product_parse"], log_text)
                self.assertNotIn("Rose Oil", log_text)
                self.assertNotIn("敏感备注 secret", log_text)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
