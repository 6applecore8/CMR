"""离线身份仓储测试；不连接数据库或读取真实员工。"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent_core.staff_repository import StaffRepository
from agent_core.contracts import Role

TENANT = "11111111-1111-1111-1111-111111111111"
STAFF = "22222222-2222-2222-2222-222222222222"


class StaffRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value
        self.cursor.fetchone.return_value = (TENANT, STAFF, "synthetic", "sales", "hash", True, 1)
        self.repository = StaffRepository(lambda: self.connection)

    def test_login_is_parameterized_and_scoped_to_tenant(self):
        name = "synthetic' OR 1=1 --"
        result = self.repository.by_login(TENANT, name)
        self.assertEqual(result.role, Role.SALES)
        query, params = self.cursor.execute.call_args_list[1].args
        self.assertNotIn(name, query)
        self.assertEqual(params, (TENANT, name))
        self.assertIn("tenant_id = %s", query)
        self.cursor.execute.assert_any_call("SET TRANSACTION READ ONLY")
        self.connection.rollback.assert_called_once()
        self.connection.close.assert_called_once()
        self.cursor.close.assert_called_once()

    def test_id_lookup_and_missing_user(self):
        self.cursor.fetchone.return_value = None
        self.assertIsNone(self.repository.by_id(TENANT, STAFF))
        self.assertEqual(self.cursor.execute.call_args.args[1], (TENANT, STAFF))

    def test_invalid_ids_never_hit_database(self):
        self.assertIsNone(self.repository.by_id("invalid", STAFF))
        self.assertIsNone(self.repository.by_login(TENANT, ""))
        self.connection.cursor.assert_not_called()

    def test_invalid_row_and_database_errors_propagate(self):
        self.cursor.fetchone.return_value = (TENANT, STAFF, "synthetic", "superuser", "hash", True, 1)
        with self.assertRaises(ValueError):
            self.repository.by_id(TENANT, STAFF)
        self.connection.rollback.assert_called_once()
        self.connection.close.assert_called_once()
        self.cursor.execute.side_effect = RuntimeError("unavailable")
        with self.assertRaises(RuntimeError):
            self.repository.by_id(TENANT, STAFF)
