"""PostgreSQL 员工读取适配器；仅供隔离测试，尚未接入生产 HTTP 服务。"""

from contextlib import closing
from typing import Callable, Optional
from uuid import UUID

from .auth import StaffRecord
from .contracts import Role


class StaffRepository:
    """按组织读取身份。factory 每次返回一个由调用方提供的独立 DB-API 连接。

    连接账号必须由部署方限制为只读；本模块的只读事务不是权限隔离的替代。
    数据库错误和损坏的员工记录向上传递，不能伪装成用户不存在。
    """

    _COLUMNS = "tenant_id, id, login_name, role, password_hash, enabled, auth_version"
    _BY_LOGIN = f"SELECT {_COLUMNS} FROM crm_staff WHERE tenant_id = %s AND login_name = %s"
    _BY_ID = f"SELECT {_COLUMNS} FROM crm_staff WHERE tenant_id = %s AND id = %s"

    def __init__(self, connection_factory: Callable):
        self._connect = connection_factory

    @staticmethod
    def _uuid(value: str) -> Optional[str]:
        if not isinstance(value, str) or len(value) > 36:
            return None
        try:
            return str(UUID(value))
        except ValueError:
            return None

    def _read(self, query: str, params: tuple) -> Optional[StaffRecord]:
        with closing(self._connect()) as connection:
            try:
                with closing(connection.cursor()) as cursor:
                    cursor.execute("SET TRANSACTION READ ONLY")
                    cursor.execute(query, params)
                    row = cursor.fetchone()
                if row is None:
                    return None
                tenant, staff_id, login, role, password_hash, enabled, version = row
                tenant_id, user_id = self._uuid(str(tenant)), self._uuid(str(staff_id))
                if (not tenant_id or not user_id or not isinstance(login, str) or not login
                        or not isinstance(password_hash, str) or not password_hash
                        or type(enabled) is not bool or type(version) is not int or version < 1):
                    raise ValueError("invalid staff record")
                return StaffRecord(user_id, tenant_id, login, Role(role), password_hash, enabled, version)
            finally:
                connection.rollback()

    def by_login(self, tenant_id: str, login_name: str) -> Optional[StaffRecord]:
        tenant = self._uuid(tenant_id)
        if not tenant or not isinstance(login_name, str) or not login_name or len(login_name) > 150:
            return None
        return self._read(self._BY_LOGIN, (tenant, login_name))

    def by_id(self, tenant_id: str, user_id: str) -> Optional[StaffRecord]:
        tenant, staff = self._uuid(tenant_id), self._uuid(user_id)
        if not tenant or not staff:
            return None
        return self._read(self._BY_ID, (tenant, staff))
