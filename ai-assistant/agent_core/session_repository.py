"""Candidate PostgreSQL session storage; not connected to the legacy HTTP service."""

from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Callable, Optional
from uuid import UUID

from .contracts import Role


@dataclass(frozen=True)
class StoredSession:
    token_hash: str = field(repr=False)
    tenant_id: str
    user_id: str
    csrf_hash: str = field(repr=False)
    role: Role
    auth_version: int
    expires_at: datetime


class SessionRepository:
    """Persist only digests; connection factory must use appropriately restricted credentials."""

    def __init__(self, connection_factory: Callable):
        self._connect = connection_factory

    @staticmethod
    def _digest(value: str) -> bool:
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None

    @staticmethod
    def _uuid(value: str) -> str:
        if not isinstance(value, str) or len(value) > 36:
            raise ValueError("invalid session identifier")
        try:
            return str(UUID(value))
        except ValueError as exc:
            raise ValueError("invalid session identifier") from exc

    @classmethod
    def _validate(cls, session: StoredSession) -> tuple:
        if (not isinstance(session, StoredSession) or not cls._digest(session.token_hash)
                or not cls._digest(session.csrf_hash) or not isinstance(session.role, Role)
                or type(session.auth_version) is not int or session.auth_version < 1
                or not isinstance(session.expires_at, datetime) or session.expires_at.utcoffset() is None):
            raise ValueError("invalid session record")
        return (session.token_hash, cls._uuid(session.tenant_id), cls._uuid(session.user_id),
                session.csrf_hash, session.role.value, session.auth_version, session.expires_at)

    def create(self, session: StoredSession) -> None:
        params = self._validate(session)
        with closing(self._connect()) as connection:
            try:
                with closing(connection.cursor()) as cursor:
                    cursor.execute("INSERT INTO crm_session (token_hash, tenant_id, staff_id, csrf_hash, "
                                   "role_snapshot, auth_version, expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s)", params)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def get(self, token_hash: str) -> Optional[StoredSession]:
        if not self._digest(token_hash):
            return None
        with closing(self._connect()) as connection:
            try:
                with closing(connection.cursor()) as cursor:
                    cursor.execute("SET TRANSACTION READ ONLY")
                    cursor.execute("SELECT token_hash, tenant_id, staff_id, csrf_hash, role_snapshot, auth_version, expires_at "
                                   "FROM crm_session WHERE token_hash = %s AND revoked_at IS NULL AND expires_at > now()",
                                   (token_hash,))
                    row = cursor.fetchone()
                if row is None:
                    return None
                token, tenant, user, csrf, role, version, expires = row
                session = StoredSession(token, str(tenant), str(user), csrf, Role(role), version, expires)
                self._validate(session)
                if token != token_hash:
                    raise ValueError("session record does not match lookup")
                return session
            finally:
                connection.rollback()

    def revoke(self, token_hash: str) -> None:
        if not self._digest(token_hash):
            return
        with closing(self._connect()) as connection:
            try:
                with closing(connection.cursor()) as cursor:
                    cursor.execute("UPDATE crm_session SET revoked_at = now() WHERE token_hash = %s AND revoked_at IS NULL",
                                   (token_hash,))
                connection.commit()
            except Exception:
                connection.rollback()
                raise
