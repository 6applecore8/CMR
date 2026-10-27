"""会话测试仅使用内存与合成账号；未连接数据库或旧 HTTP 服务。"""
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent_core.auth import AuthenticationService, StaffRecord
from agent_core.contracts import DomainError, Role
from agent_core.credentials import hash_password


class AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = hash_password("example-password")

    def setUp(self):
        self.now = 1000.0
        self.user = StaffRecord("sales-id", "org-id", "sales-login", Role.SALES, self.password_hash)
        self.service = AuthenticationService(self.by_login, self.by_id, now=lambda: self.now, ttl_seconds=60)

    def by_login(self, tenant, login):
        return self.user if self.user is not None and (tenant, login) == (self.user.tenant_id, self.user.login_name) else None

    def by_id(self, tenant, ident):
        return self.user if self.user is not None and (tenant, ident) == (self.user.tenant_id, self.user.user_id) else None

    def login(self):
        return self.service.login("org-id", "sales-login", "example-password", "local-source")

    def assert_code(self, code, callback):
        with self.assertRaises(DomainError) as result:
            callback()
        self.assertEqual(code, result.exception.code)

    def test_login_creates_non_logged_distinct_tokens_and_csrf_required(self):
        login = self.login()
        self.assertNotIn(login.token, repr(login))
        self.assertNotIn(login.csrf, repr(login))
        self.assertEqual(Role.SALES, self.service.principal(login.token).role)
        self.assert_code("CSRF_REJECTED", lambda: self.service.principal(login.token, csrf="bad", require_csrf=True))
        self.assertEqual("sales-id", self.service.principal(login.token, csrf=login.csrf, require_csrf=True).user_id)
        self.assertNotIn(login.token, repr(self.service._sessions))
        self.assertNotIn(login.csrf, repr(self.service._sessions))

    def test_revoked_expired_and_disabled_sessions(self):
        result = self.login()
        self.service.logout(result.token)
        self.assert_code("AUTH_REQUIRED", lambda: self.service.principal(result.token))
        result = self.login()
        self.user = replace(self.user, enabled=False)
        self.assert_code("AUTH_REQUIRED", lambda: self.service.principal(result.token))
        self.user = replace(self.user, enabled=True)
        self.now += 60
        self.assert_code("AUTH_REQUIRED", lambda: self.service.principal(result.token))

    def test_auth_version_and_role_are_read_from_current_repository(self):
        result = self.login()
        self.user = replace(self.user, role=Role.MANAGER)
        self.assert_code("AUTH_REQUIRED", lambda: self.service.principal(result.token))
        self.user = replace(self.user, role=Role.SALES, auth_version=2)
        self.assert_code("AUTH_REQUIRED", lambda: self.service.principal(result.token))

    def test_unknown_disabled_and_wrong_password_share_error(self):
        self.assert_code("AUTH_FAILED", lambda: self.service.login("org-id", "missing", "wrong", "one"))
        self.assert_code("AUTH_FAILED", lambda: self.service.login("org-id", "sales-login", "wrong", "two"))
        self.user = replace(self.user, enabled=False)
        self.assert_code("AUTH_FAILED", lambda: self.service.login("org-id", "sales-login", "example-password", "three"))

    def test_rate_limit_resets_after_window(self):
        for _ in range(5):
            self.assert_code("AUTH_FAILED", lambda: self.service.login("org-id", "sales-login", "wrong", "source"))
        self.assert_code("AUTH_RATE_LIMITED", lambda: self.service.login("org-id", "sales-login", "example-password", "source"))
        self.now += 901
        self.assertTrue(self.service.login("org-id", "sales-login", "example-password", "source").token)

    def test_token_format_is_bounded(self):
        for value in (None, "", "x" * 257, "x" * 20 + "\ud800"):
            self.assert_code("AUTH_REQUIRED", lambda: self.service.principal(value))
            self.service.logout(value)

    def test_wrong_tenant_and_deleted_account_cannot_authenticate(self):
        self.assert_code("AUTH_FAILED", lambda: self.service.login("other", "sales-login", "example-password", "source"))
        result = self.login()
        self.user = None
        self.assert_code("AUTH_REQUIRED", lambda: self.service.principal(result.token))


if __name__ == "__main__":
    unittest.main()