"""预检使用独立合成文件，不接触真实客户或输出客户内容。"""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent_core.migration_preflight import _check_file, inspect_source, main, MAX_FILE_BYTES


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="cmr-preflight-fixture-"))

    def populate(self):
        (self.root / "clients").mkdir()
        (self.root / "leads").mkdir()
        (self.root / "clients" / "_index.md").write_text("# synthetic index", encoding="utf-8")
        (self.root / "leads" / "pipeline.md").write_text("# synthetic pipeline", encoding="utf-8")

    def test_absent_sources_are_not_zero(self):
        result = inspect_source(self.root)
        self.assertEqual("UNAVAILABLE", result["state"])
        self.assertIsNone(result["profiles"])
        self.assertFalse(result["migrationAllowed"])

    def test_complete_synthetic_files_never_auto_authorize_migration(self):
        self.populate()
        (self.root / "clients" / "synthetic.md").write_text("private-test-record", encoding="utf-8")
        result = inspect_source(self.root)
        self.assertEqual("READABLE_REQUIRES_REVIEW", result["state"])
        self.assertEqual(1, result["profiles"]["total"])
        self.assertEqual("UNRESOLVED", result["ownership"])
        self.assertFalse(result["migrationAllowed"])
        self.assertNotIn("private-test-record", json.dumps(result))
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertNotIn("synthetic.md", json.dumps(result))

    def test_missing_index_is_not_valid_empty_source(self):
        self.populate()
        alternate = self.root / "clients" / "_index.md"
        alternate.write_bytes(b"\xff")
        result = inspect_source(self.root)
        self.assertEqual("UNAVAILABLE", result["state"])
        self.assertEqual("invalid_utf8", result["index"])

    def test_corrupt_profile_fails_closed(self):
        self.populate()
        (self.root / "clients" / "bad.md").write_bytes(b"\xff")
        result = inspect_source(self.root)
        self.assertEqual("UNAVAILABLE", result["state"])
        self.assertEqual({"invalid_utf8": 1}, result["profiles"]["issues"])

    def test_oversized_profile_fails_closed(self):
        self.populate()
        (self.root / "clients" / "large.md").write_bytes(b"x" * (MAX_FILE_BYTES + 1))
        result = inspect_source(self.root)
        self.assertEqual({"too_large": 1}, result["profiles"]["issues"])
        self.assertEqual("UNAVAILABLE", result["state"])

    def test_total_read_budget_fails_closed(self):
        self.populate()
        (self.root / "clients" / "sample.md").write_text("synthetic", encoding="utf-8")
        with patch("agent_core.migration_preflight.MAX_TOTAL_BYTES", 1):
            result = inspect_source(self.root)
        self.assertEqual("UNAVAILABLE", result["state"])
        self.assertEqual("source_size_limit_exceeded", result["reason"])
        self.assertIsNone(result["profiles"])
    def test_read_failure_is_not_empty(self):
        self.populate()
        with patch("agent_core.migration_preflight.os.scandir", side_effect=PermissionError("private")):
            result = inspect_source(self.root)
        self.assertEqual("source_unreadable", result["reason"])
        self.assertNotIn("private", json.dumps(result))

    def test_cli_returns_failure_for_missing_data(self):
        with patch.object(sys, "argv", ["preflight", "--root", str(self.root)]), patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(2, main())
        self.assertEqual("UNAVAILABLE", json.loads(out.getvalue())["state"])

    def test_links_rejected_without_reading_target(self):
        with patch.object(Path, "is_symlink", return_value=True):
            self.assertEqual("root_link_rejected", inspect_source(self.root)["reason"])
            self.assertEqual("link_rejected", _check_file(self.root / "unused"))


if __name__ == "__main__":
    unittest.main()