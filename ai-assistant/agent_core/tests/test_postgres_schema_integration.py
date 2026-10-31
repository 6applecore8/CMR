"""Opt-in PostgreSQL schema checks, using synthetic data in a rolled-back transaction.

Set CMR_TEST_POSTGRES_DSN only for a dedicated database named cmr_test_* and
install psycopg 3 separately. No SQL is run against a differently named database.
This suite does not prove application-role permissions or HTTP authorization.
"""

import os
from pathlib import Path
import re
import unittest
from uuid import uuid4


def _migration_body(text: str) -> str:
    """Keep the migration inside the test transaction, without its outer wrapper."""
    text, starts = re.subn(r"(?m)^BEGIN;\s*$", "", text, count=1)
    text, ends = re.subn(r"(?m)^COMMIT;\s*$", "", text, count=1)
    if starts != 1 or ends != 1 or re.search(r"(?mi)^\s*(BEGIN|COMMIT|ROLLBACK)\s*;", text):
        raise ValueError("unexpected migration transaction wrapper")
    return text


def _require_test_database(name: str) -> None:
    if not isinstance(name, str) or not re.fullmatch(r"cmr_test_[a-z0-9_]+", name):
        raise ValueError("PostgreSQL integration tests require a dedicated cmr_test_* database")


class MigrationWrapperTests(unittest.TestCase):
    def test_transaction_wrapper_is_required_and_not_nested(self):
        self.assertEqual(_migration_body("BEGIN;\nSELECT 1;\nCOMMIT;"), "\nSELECT 1;\n")
        for script in ("SELECT 1;", "BEGIN;\nCOMMIT;\nCOMMIT;"):
            with self.assertRaises(ValueError):
                _migration_body(script)

    def test_checked_in_migration_has_supported_wrapper(self):
        migration = Path(__file__).resolve().parents[1] / "migrations" / "V001__business_foundation.sql"
        self.assertIn("CREATE TABLE crm_staff", _migration_body(migration.read_text(encoding="utf-8")))

    def test_only_explicit_test_database_name_is_accepted(self):
        _require_test_database("cmr_test_synthetic_1")
        for name in ("postgres", "cmr", "cmr_test_", "cmr_test_prod;DROP", None):
            with self.assertRaises(ValueError):
                _require_test_database(name)


@unittest.skipUnless(os.environ.get("CMR_TEST_POSTGRES_DSN"), "dedicated PostgreSQL test DSN not configured")
class PostgresSchemaIntegrationTests(unittest.TestCase):
    def test_schema_constraints_in_rolled_back_transaction(self):
        try:
            import psycopg
            from psycopg import sql
        except ImportError as exc:
            self.fail("Install psycopg 3 before running the opt-in PostgreSQL tests")

        migration = Path(__file__).resolve().parents[1] / "migrations" / "V001__business_foundation.sql"
        body = _migration_body(migration.read_text(encoding="utf-8"))
        # A bad connection or database name fails before CREATE SCHEMA or any DML.
        connection = psycopg.connect(os.environ["CMR_TEST_POSTGRES_DSN"])
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database()")
                name = cursor.fetchone()[0]
                _require_test_database(name)
                schema = "cmr_verify_" + uuid4().hex
                cursor.execute(sql.SQL("CREATE SCHEMA {} ").format(sql.Identifier(schema)))
                cursor.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(schema)))
                cursor.execute(body)
                tenant, staff, other_tenant = uuid4(), uuid4(), uuid4()
                cursor.execute("INSERT INTO crm_tenant (id, name) VALUES (%s, %s), (%s, %s)",
                               (tenant, "Test tenant", other_tenant, "Other tenant"))
                cursor.execute("INSERT INTO crm_staff (tenant_id, id, login_name, password_hash, role) "
                               "VALUES (%s, %s, %s, %s, %s)",
                               (tenant, staff, "synthetic", "synthetic-hash", "sales"))
                cursor.execute("SELECT login_name FROM crm_staff WHERE tenant_id = %s AND id = %s", (tenant, staff))
                self.assertEqual(cursor.fetchone()[0], "synthetic")
                cursor.execute("SAVEPOINT invalid_reference")
                with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                    cursor.execute("INSERT INTO crm_customer (tenant_id, id, owner_staff_id, channel) "
                                   "VALUES (%s, %s, %s, %s)", (other_tenant, uuid4(), staff, "email"))
                cursor.execute("ROLLBACK TO SAVEPOINT invalid_reference")
                cursor.execute("SAVEPOINT invalid_role")
                with self.assertRaises(psycopg.errors.CheckViolation):
                    cursor.execute("INSERT INTO crm_staff (tenant_id, id, login_name, password_hash, role) "
                                   "VALUES (%s, %s, %s, %s, %s)",
                                   (tenant, uuid4(), "other", "synthetic-hash", "admin"))
                cursor.execute("ROLLBACK TO SAVEPOINT invalid_role")
        finally:
            connection.rollback()
            connection.close()


if __name__ == "__main__":
    unittest.main()
