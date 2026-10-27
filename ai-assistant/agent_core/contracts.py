"""可信身份与结果契约；调用方必须先鉴权，不能从模型参数构造身份。"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class DomainError(ValueError):
    """可映射到 HTTP 的领域错误；消息不包含客户数据或内部异常。"""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class Role(str, Enum):
    SALES = "sales"
    MANAGER = "manager"


@dataclass(frozen=True)
class Principal:
    """认证层提供的员工身份；该对象本身不是登录或令牌验证机制。"""

    user_id: str
    tenant_id: str
    role: Role

    def __post_init__(self) -> None:
        if (not isinstance(self.role, Role)
            or any(not isinstance(v, str) or not v.strip() or v != v.strip() or len(v) > 160
                   or any(ord(c) < 32 for c in v) for v in (self.user_id, self.tenant_id))):
            raise DomainError("INVALID_PRINCIPAL", "需要有效的员工身份", 401)

    def require_manager(self) -> None:
        """限制管理动作；业务员不能通过请求参数自称管理员。"""
        if self.role is not Role.MANAGER:
            raise DomainError("FORBIDDEN", "此操作需要管理权限", 403)


def validate_args(args: Mapping[str, Any], allowed: set[str]) -> dict[str, Any]:
    """拒绝未知参数，避免 SQL、组织或权限字段被模型夹带进工具。"""
    if not isinstance(args, Mapping) or any(key not in allowed for key in args):
        raise DomainError("INVALID_ARGUMENT", "工具参数不符合约定")
    return dict(args)


def text_arg(value: Any, name: str, *, required: bool = False, limit: int = 160) -> str:
    """校验有界文本；不自动把对象转换成字符串而掩盖类型错误。"""
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise DomainError("INVALID_ARGUMENT", f"{name} 必须为有效文本")
    value = value.strip()
    if required and not value:
        raise DomainError("INVALID_ARGUMENT", f"缺少 {name}")
    return value


def result(data: dict[str, Any], trace_id: str) -> dict[str, Any]:
    """结构化事实为主；不在此生成或记录包含隐私的模型解释。"""
    return {"code": 0, "message": "ok", "data": data, "traceId": trace_id}


def utc_now() -> datetime:
    """返回带时区的服务端时间；生产入口不接受用户覆盖查询时钟。"""
    return datetime.now(timezone.utc)
