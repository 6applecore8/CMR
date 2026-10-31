"""可测试的认证与会话领域规则；仅内存实现，不是已部署的 HTTP 登录。"""

import hashlib
import hmac
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .contracts import DomainError, Principal, Role
from .credentials import hash_password, verify_password


@dataclass(frozen=True)
class StaffRecord:
    """身份来自可信用户仓储；不接收模型或浏览器提交的角色。"""
    user_id: str
    tenant_id: str
    login_name: str
    role: Role
    password_hash: str = field(repr=False)
    enabled: bool = True
    auth_version: int = 1


@dataclass(frozen=True)
class _Session:
    tenant_id: str
    user_id: str
    csrf_hash: str
    role: Role
    auth_version: int
    expires_at: float


@dataclass(frozen=True)
class LoginResult:
    """明文票据仅返回给入口层一次，不写入日志、repr 或仓储。"""
    token: str = field(repr=False)
    csrf: str = field(repr=False)
    expires_at: float


class AuthenticationService:
    """供单进程测试的会话服务；正式部署须用共享持久仓储和全局限流。"""

    def __init__(self, by_login: Callable[[str, str], Optional[StaffRecord]],
                 by_id: Callable[[str, str], Optional[StaffRecord]], *,
                 now: Callable[[], float] = time.time, ttl_seconds: int = 3600):
        if type(ttl_seconds) is not int or not 60 <= ttl_seconds <= 86400:
            raise ValueError("invalid session lifetime")
        self._by_login, self._by_id, self._now, self._ttl = by_login, by_id, now, ttl_seconds
        self._dummy_hash = hash_password(secrets.token_urlsafe(24))
        self._sessions: dict[str, _Session] = {}
        self._attempts: dict[tuple[str, str], list[float]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _valid_id(value: str) -> bool:
        return isinstance(value, str) and 0 < len(value) <= 160 and value == value.strip() and not any(ord(c) < 32 for c in value)

    def _store_session(self, digest: str, session: _Session, now: float) -> None:
        """Called with the process lock held; default implementation is in-memory."""
        self._sessions = {k: v for k, v in self._sessions.items() if now < v.expires_at}
        if len(self._sessions) >= 10000:
            raise DomainError("AUTH_RATE_LIMITED", "认证服务繁忙，请稍后重试", 429)
        self._sessions[digest] = session

    def _get_session(self, digest: str) -> Optional[_Session]:
        return self._sessions.get(digest)

    def _remove_session(self, digest: str) -> None:
        self._sessions.pop(digest, None)

    def login(self, tenant_id: str, login_name: str, password: str, source_id: str) -> LoginResult:
        """错误统一返回，固定失败预算；source_id 必须由入口层可信地提供。"""
        if not all(self._valid_id(v) for v in (tenant_id, login_name, source_id)):
            raise DomainError("AUTH_FAILED", "账号或密码错误", 401)
        now = self._now()
        key = (tenant_id + "\x00" + login_name, source_id)
        with self._lock:
            self._attempts = {k: [t for t in values if now - t < 900]
                              for k, values in self._attempts.items() if any(now - t < 900 for t in values)}
            if len(self._attempts.get(key, [])) >= 5:
                raise DomainError("AUTH_RATE_LIMITED", "尝试次数过多，请稍后重试", 429)
            if key not in self._attempts and len(self._attempts) >= 10000:
                raise DomainError("AUTH_RATE_LIMITED", "认证服务繁忙，请稍后重试", 429)
            # 先保留名额，避免多个并发请求在慢哈希期间同时绕过限制。
            self._attempts.setdefault(key, []).append(now)
        staff = self._by_login(tenant_id, login_name)
        valid_hash = verify_password(password, staff.password_hash if staff is not None else self._dummy_hash)
        if (staff is None or staff.tenant_id != tenant_id or staff.login_name != login_name or not staff.enabled
                or not isinstance(staff.role, Role) or type(staff.auth_version) is not int or staff.auth_version < 1
                or not self._valid_id(staff.user_id) or not valid_hash):
            raise DomainError("AUTH_FAILED", "账号或密码错误", 401)
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        session = _Session(tenant_id, staff.user_id, self._digest(csrf), staff.role, staff.auth_version, now + self._ttl)
        with self._lock:
            self._attempts.pop(key, None)
            self._store_session(self._digest(token), session, now)
        return LoginResult(token, csrf, session.expires_at)

    def principal(self, token: str, *, csrf: str | None = None, require_csrf: bool = False) -> Principal:
        """每次查最新员工状态和版本；修改角色、禁用或撤销后不能凭旧缓存越权。"""
        if not isinstance(token, str) or re.fullmatch(r"[A-Za-z0-9_-]{16,256}", token) is None:
            raise DomainError("AUTH_REQUIRED", "请先登录", 401)
        digest = self._digest(token)
        with self._lock:
            session = self._get_session(digest)
            if session is None:
                raise DomainError("AUTH_REQUIRED", "请先登录", 401)
            if self._now() >= session.expires_at:
                self._remove_session(digest)
                raise DomainError("AUTH_REQUIRED", "请先登录", 401)
        staff = self._by_id(session.tenant_id, session.user_id)
        if (staff is None or not staff.enabled or staff.tenant_id != session.tenant_id
                or staff.user_id != session.user_id or type(staff.auth_version) is not int
                or staff.auth_version != session.auth_version or staff.role != session.role
                or not isinstance(staff.role, Role)):
            raise DomainError("AUTH_REQUIRED", "请先登录", 401)
        if require_csrf and (not isinstance(csrf, str) or re.fullmatch(r"[A-Za-z0-9_-]{16,256}", csrf) is None
                             or not hmac.compare_digest(session.csrf_hash, self._digest(csrf))):
            raise DomainError("CSRF_REJECTED", "请求校验失败", 403)
        return Principal(staff.user_id, staff.tenant_id, staff.role)

    def logout(self, token: str) -> None:
        """撤销当前会话；无效票据不泄露账号状态。"""
        if isinstance(token, str) and re.fullmatch(r"[A-Za-z0-9_-]{16,256}", token) is not None:
            with self._lock:
                self._remove_session(self._digest(token))
