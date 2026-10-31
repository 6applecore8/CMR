"""Candidate persistent authentication; not a deployed HTTP authentication layer.

The inherited attempt limiter is process-local and is not suitable for a multi-process
deployment. An external shared limiter and HTTP/CSRF integration remain mandatory.
"""

from datetime import datetime, timezone

from .auth import AuthenticationService, _Session
from .session_repository import SessionRepository, StoredSession


class PersistentAuthenticationService(AuthenticationService):
    def __init__(self, by_login, by_id, sessions: SessionRepository, **kwargs):
        if not isinstance(sessions, SessionRepository):
            raise TypeError("persistent session repository required")
        super().__init__(by_login, by_id, **kwargs)
        self._session_repository = sessions

    def _store_session(self, digest: str, session: _Session, now: float) -> None:
        self._session_repository.create(StoredSession(
            digest, session.tenant_id, session.user_id, session.csrf_hash, session.role,
            session.auth_version, datetime.fromtimestamp(session.expires_at, timezone.utc)))

    def _get_session(self, digest: str) -> _Session | None:
        row = self._session_repository.get(digest)
        if row is None:
            return None
        return _Session(row.tenant_id, row.user_id, row.csrf_hash, row.role,
                        row.auth_version, row.expires_at.timestamp())

    def _remove_session(self, digest: str) -> None:
        self._session_repository.revoke(digest)
