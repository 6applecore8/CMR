"""密码哈希工具：仅负责哈希校验，不提供登录、会话或用户管理。"""

import base64
import hashlib
import hmac
import secrets

ITERATIONS = 600_000
MIN_ITERATIONS = 100_000
MAX_ITERATIONS = 2_000_000


def _password_bytes(password: str) -> bytes:
    if not isinstance(password, str) or not password or len(password) > 256:
        raise ValueError("invalid password")
    return password.encode("utf-8")


def hash_password(password: str) -> str:
    """生成独立随机盐；哈希格式包含算法和迭代次数以便未来升级。"""
    raw = _password_bytes(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", raw, salt, ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        ITERATIONS, base64.b64encode(salt).decode("ascii"), base64.b64encode(digest).decode("ascii"))


def verify_password(password: str, encoded: str) -> bool:
    """参数异常和损坏的哈希一律认证失败；不输出密码或哈希。"""
    try:
        raw = _password_bytes(password)
        if not isinstance(encoded, str) or len(encoded) > 300:
            return False
        algorithm, raw_iterations, raw_salt, raw_digest = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or not raw_iterations.isascii() or not raw_iterations.isdecimal():
            return False
        count = int(raw_iterations)
        if not MIN_ITERATIONS <= count <= MAX_ITERATIONS:
            return False
        salt = base64.b64decode(raw_salt, validate=True)
        expected = base64.b64decode(raw_digest, validate=True)
        if len(salt) != 16 or len(expected) != 32:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", raw, salt, count)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, OverflowError, UnicodeError):
        return False