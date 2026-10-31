"""Opt-in live staff repository checks on an explicitly disposable PostgreSQL cluster.

This test commits a randomly named schema, synthetic rows and a restricted LOGIN
role. They are deliberately retained for operator review; it never drops them.
Use only a dedicated cluster and set CMR_TEST_ALLOW_ROLE_CREATION=1 explicitly.
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from uuid import uuid4

from agent_core.auth import AuthenticationService
from agent_core.contracts import DomainError, Role
from agent_core.credentials import hash_password
from agent_core.persistent_auth import PersistentAuthenticationService
from agent_core.staff_repository import StaffRepository
from agent_core.session_repository import SessionRepository, StoredSession
from agent_core.tests.test_postgres_schema_integration import _migration_body, _require_test_database


@unittest.skipUnless(
    os.environ.get("CMR_TEST_POSTGRES_DSN") and os.environ.get("CMR_TEST_ALLOW_ROLE_CREATION") == "1",
    "dedicated disposable test cluster and explicit role-creation opt-in required",
)
class StaffPostgresIntegrationTests(unittest.TestCase):
    def test_restricted_login_repository_and_revocation(self):
        try:
            import psycopg
            from psycopg import sql
            from psycopg.conninfo import make_conninfo
        except ImportError:
            self.fail("Install psycopg 3 before running the opt-in PostgreSQL tests")

        admin_dsn = os.environ["CMR_TEST_POSTGRES_DSN"]
        suffix = uuid4().hex
        schema, role = "cmr_staff_test_" + suffix, "cmr_reader_" + suffix
        tenant, other_tenant, staff = str(uuid4()), str(uuid4()), str(uuid4())
        migration = Path(__file__).resolve().parents[1] / "migrations" / "V001__business_foundation.sql"
        body = _migration_body(migration.read_text(encoding="utf-8"))
        session_migration = migration.with_name("V002__session_security.sql")
        session_body = _migration_body(session_migration.read_text(encoding="utf-8"))
        admin = psycopg.connect(admin_dsn)
        try:
            with admin.cursor() as cursor:
                cursor.execute("SELECT current_database()")
                _require_test_database(cursor.fetchone()[0])
                cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
                cursor.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(schema)))
                cursor.execute(body)
                cursor.execute(session_body)
                cursor.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS").format(sql.Identifier(role)))
                cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(schema), sql.Identifier(role)))
                cursor.execute(sql.SQL("GRANT SELECT ON {}.crm_staff TO {}").format(sql.Identifier(schema), sql.Identifier(role)))
                cursor.execute(sql.SQL("GRANT SELECT, INSERT ON {}.crm_session TO {}").format(sql.Identifier(schema), sql.Identifier(role)))
                cursor.execute(sql.SQL("GRANT UPDATE (revoked_at) ON {}.crm_session TO {}").format(sql.Identifier(schema), sql.Identifier(role)))
                cursor.execute("INSERT INTO crm_tenant (id, name) VALUES (%s, %s), (%s, %s)",
                               (tenant, "Synthetic tenant", other_tenant, "Synthetic other tenant"))
                cursor.execute("INSERT INTO crm_staff (tenant_id,id,login_name,password_hash,role) VALUES (%s,%s,%s,%s,%s)",
                               (tenant, staff, "synthetic-login", hash_password("synthetic password"), "sales"))
            admin.commit()

            reader_dsn = make_conninfo(admin_dsn, user=role, options="-csearch_path=" + schema)
            with psycopg.connect(reader_dsn) as reader:
                with reader.cursor() as cursor:
                    cursor.execute("SELECT current_user, has_table_privilege(current_user, %s, 'SELECT'), "
                                   "has_table_privilege(current_user, %s, 'INSERT'), "
                                   "has_table_privilege(current_user, %s, 'SELECT'), "
                                   "has_column_privilege(current_user, %s, 'revoked_at', 'UPDATE'), "
                                   "has_column_privilege(current_user, %s, 'csrf_hash', 'UPDATE'), "
                                   "has_table_privilege(current_user, %s, 'DELETE')",
                                   (schema + ".crm_staff", schema + ".crm_staff", schema + ".crm_customer",
                                    schema + ".crm_session", schema + ".crm_session", schema + ".crm_session"))
                    self.assertEqual(cursor.fetchone(), (role, True, False, False, True, False, False))

            repository = StaffRepository(lambda: psycopg.connect(reader_dsn))
            self.assertEqual(repository.by_login(tenant, "synthetic-login").role, Role.SALES)
            self.assertEqual(repository.by_id(tenant, staff).user_id, staff)
            self.assertIsNone(repository.by_login(other_tenant, "synthetic-login"))
            self.assertIsNone(repository.by_login(tenant, "synthetic-login' OR '1'='1"))
            service = AuthenticationService(repository.by_login, repository.by_id)
            login = service.login(tenant, "synthetic-login", "synthetic password", "synthetic-source")
            self.assertEqual(service.principal(login.token).user_id, staff)

            sessions = SessionRepository(lambda: psycopg.connect(reader_dsn))
            stored = StoredSession("a" * 64, tenant, staff, "b" * 64, Role.SALES, 1,
                                   datetime.now(timezone.utc) + timedelta(minutes=5))
            sessions.create(stored)
            self.assertEqual(sessions.get(stored.token_hash), stored)
            self.assertNotIn(stored.token_hash, repr(stored))
            sessions.revoke(stored.token_hash)
            self.assertIsNone(sessions.get(stored.token_hash))
            expired = StoredSession("c" * 64, tenant, staff, "d" * 64, Role.SALES, 1,
                                    datetime.now(timezone.utc) - timedelta(seconds=1))
            sessions.create(expired)
            self.assertIsNone(sessions.get(expired.token_hash))

            first_process = PersistentAuthenticationService(repository.by_login, repository.by_id, sessions)
            persisted_login = first_process.login(tenant, "synthetic-login", "synthetic password", "synthetic-source")
            second_process = PersistentAuthenticationService(repository.by_login, repository.by_id, sessions)
            self.assertEqual(second_process.principal(persisted_login.token, csrf=persisted_login.csrf,
                                                      require_csrf=True).user_id, staff)
            with self.assertRaises(DomainError) as error:
                second_process.principal(persisted_login.token, csrf="x" * 32, require_csrf=True)
            self.assertEqual(error.exception.code, "CSRF_REJECTED")
            second_process.logout(persisted_login.token)
            with self.assertRaises(DomainError):
                first_process.principal(persisted_login.token)
            disabled_login = first_process.login(tenant, "synthetic-login", "synthetic password", "another-source")

            with admin.cursor() as cursor:
                cursor.execute(sql.SQL("UPDATE {}.crm_staff SET enabled = FALSE WHERE tenant_id = %s AND id = %s")
                               .format(sql.Identifier(schema)), (tenant, staff))
            admin.commit()
            with self.assertRaises(DomainError) as error:
                service.principal(login.token)
            self.assertEqual(error.exception.code, "AUTH_REQUIRED")
            with self.assertRaises(DomainError) as error:
                second_process.principal(disabled_login.token)
            self.assertEqual(error.exception.code, "AUTH_REQUIRED")
        finally:
            admin.rollback()
            admin.close()


if __name__ == "__main__":
    unittest.main()
