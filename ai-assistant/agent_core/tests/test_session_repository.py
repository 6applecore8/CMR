"""Synthetic transaction and validation tests for the candidate session store."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import MagicMock

from agent_core.contracts import Role
from agent_core.session_repository import SessionRepository, StoredSession


class SessionRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value
        self.repository = SessionRepository(lambda: self.connection)
        self.session = StoredSession("a" * 64, "11111111-1111-1111-1111-111111111111",
                                     "22222222-2222-2222-2222-222222222222", "b" * 64,
                                     Role.SALES, 1, datetime.now(timezone.utc) + timedelta(minutes=5))

    def test_create_is_parameterized_and_committed(self):
        self.repository.create(self.session)
        query, params = self.cursor.execute.call_args.args
        self.assertNotIn(self.session.token_hash, query)
        self.assertEqual(params[0], self.session.token_hash)
        self.connection.commit.assert_called_once()
        self.connection.close.assert_called_once()
        self.assertNotIn(self.session.csrf_hash, repr(self.session))

    def test_invalid_values_never_connect(self):
        for session in (replace(self.session, token_hash="raw token"),
                        replace(self.session, csrf_hash="B" * 64),
                        replace(self.session, auth_version=True),
                        replace(self.session, expires_at=datetime(2030, 1, 1)),
                        replace(self.session, tenant_id="invalid")):
            with self.assertRaises(ValueError):
                self.repository.create(session)
        self.assertIsNone(self.repository.get("invalid"))
        self.repository.revoke("invalid")
        self.connection.cursor.assert_not_called()

    def test_database_failure_rolls_back_and_propagates(self):
        self.cursor.execute.side_effect = RuntimeError("database unavailable")
        with self.assertRaises(RuntimeError):
            self.repository.create(self.session)
        self.connection.rollback.assert_called_once()
        self.connection.close.assert_called_once()
        self.connection.commit.assert_not_called()

    def test_get_uses_read_only_transaction_and_rejects_bad_rows(self):
        self.cursor.fetchone.return_value = (self.session.token_hash, self.session.tenant_id,
            self.session.user_id, self.session.csrf_hash, self.session.role.value,
            self.session.auth_version, self.session.expires_at)
        self.assertEqual(self.repository.get(self.session.token_hash), self.session)
        self.cursor.execute.assert_any_call("SET TRANSACTION READ ONLY")
        self.connection.rollback.assert_called_once()
        self.cursor.fetchone.return_value = ("c" * 64, *self.cursor.fetchone.return_value[1:])
        with self.assertRaises(ValueError):
            self.repository.get(self.session.token_hash)


if __name__ == "__main__":
    unittest.main()
