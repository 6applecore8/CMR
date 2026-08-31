"""本地客户 CRM 看板的标准库后端。

数据主源仍是 ``clients/*.md``、``clients/_index.md`` 和
``leads/pipeline.md``。本模块同时提供可直接测试的 Markdown 解析、合并、
新建和更新函数，HTTP 层只负责把这些能力暴露成 JSON API。
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import io
import json
import mimetypes
import re
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple
from urllib.parse import parse_qs, unquote, urlsplit


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
CLIENTS_DIR = PROJECT_DIR / "clients"
LEADS_DIR = PROJECT_DIR / "leads"
INDEX_PATH = CLIENTS_DIR / "_index.md"
PIPELINE_PATH = LEADS_DIR / "pipeline.md"

STATIC_FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/styles.css": "styles.css",
    "/app.js": "app.js",
}

KNOWN_STATUSES: Tuple[str, ...] = (
    "new",
    "researched",
    "outreach_1",
    "outreach_2",
    "outreach_3",
    "replied",
    "sampling",
    "quoting",
    "paid",
    "won",
    "lost",
    "disqualified",
    "cold",
)
STATUS_ORDER = {value: index for index, value in enumerate(KNOWN_STATUSES)}
CLOSED_STATUSES = {"won", "lost", "disqualified", "cold"}

# 对外稳定的错误码。日志和 API 错误响应共用这套码，便于本机排查。
ERROR_CODES = {
    "ok": "CRM-OK-001",
    "startup": "CRM-STARTUP-001",
    "request": "CRM-REQUEST-001",
    "validation": "CRM-VALIDATION-001",
    "parse": "CRM-PARSE-001",
    "load": "CRM-LOAD-001",
    "write": "CRM-WRITE-001",
    "not_found": "CRM-NOTFOUND-001",
    "api": "CRM-API-001",
    "unexpected": "CRM-UNEXPECTED-001",
    "product_parse": "CRM-PRODUCT-PARSE-001",
    "bulk_product_parse": "CRM-BULK-PRODUCT-PARSE-001",
    "bulk_copy": "CRM-BULK-COPY-001",
    "pagination": "CRM-PAGINATION-001",
}
SENSITIVE_LOG_KEYS = {
    "email",
    "known_email",
    "phone",
    "known_phone",
    "whatsapp",
    "notes",
    "next_action",
    "address",
    "product_raw",
    "product_name",
    "fragrance_requirement",
    "product_application",
    "product_quantity",
    "product_specification",
    "target_price",
    "raw_text",
    "other_requirements",
    "product_codes",
    "product_names",
    "product_items",
    "raw_markdown",
    "content",
    "payload",
}
LOG_FILENAME = "crm-dashboard.jsonl"
EDITABLE_FIELDS = {
    "status",
    "next_action",
    "notes",
    "company",
    "contact_name",
    "title",
    "country_region",
    "address",
    "market_bucket",
    "channel_type",
    "source",
    "known_email",
    "known_phone",
    "product_interest",
    "product_raw",
    "product_codes",
    "product_names",
    "product_name",
    "fragrance_requirement",
    "product_application",
    "product_quantity",
    "product_specification",
    "target_price",
    "other_requirements",
    "icp_score",
    "icp_tier",
}
PROFILE_FIELDS: Tuple[str, ...] = (
    "client_id",
    "company",
    "contact_name",
    "title",
    "country_region",
    "address",
    "market_bucket",
    "channel_type",
    "source",
    "known_email",
    "known_phone",
    "product_interest",
    "product_raw",
    "product_codes",
    "product_names",
    "product_name",
    "fragrance_requirement",
    "product_application",
    "product_quantity",
    "product_specification",
    "target_price",
    "other_requirements",
    "icp_score",
    "icp_tier",
    "status",
    "next_action",
    "created_at",
    "updated_at",
)
PRODUCT_FIELDS: Tuple[str, ...] = (
    "product_raw",
    "product_codes",
    "product_names",
    "product_name",
    "fragrance_requirement",
    "product_application",
    "product_quantity",
    "product_specification",
    "target_price",
    "other_requirements",
)

# 解析器接受的自然语言标签。长标签在正则中优先，避免 ``product`` 抢先
# 匹配 ``product name``；FIELD_ALIASES 仍负责 Markdown/API 字段归一化。
PRODUCT_LABELS = {
    "product_name": ("product_name", "product name", "product", "品名", "产品名称", "产品"),
    "fragrance_requirement": (
        "fragrance_requirement",
        "fragrance requirement",
        "fragrance",
        "scent",
        "香型要求",
        "香型",
        "香味",
        "参考香",
    ),
    "product_application": ("product_application", "product application", "application", "use", "产品用途", "用途", "应用"),
    "product_quantity": ("product_quantity", "product quantity", "order quantity", "quantity", "qty", "产品数量", "采购量", "数量"),
    "product_specification": (
        "product_specification",
        "product specification",
        "specification",
        "spec",
        "size",
        "容量",
        "浓度",
        "包装",
        "产品规格",
        "规格",
    ),
    "target_price": ("target_price", "target price", "target", "price", "budget", "目标价格", "目标价", "目标", "价格", "预算"),
    "other_requirements": ("other_requirements", "other requirements", "requirements", "requirement", "要求", "其他要求"),
}

BULK_PRODUCT_CODE_LABELS = (
    "internal code",
    "product code",
    "item no.",
    "item no",
    "sku",
    "内部编码",
    "产品编码",
    "编码",
    "code",
)
BULK_PRODUCT_NAME_LABELS = (
    "product name",
    "产品名称",
    "品名",
    "name",
)

# 旧档案中使用过的英文、中文、简写字段名。键统一为标准 API 字段。
FIELD_ALIASES = {
    "client_id": "client_id",
    "client id": "client_id",
    "company": "company",
    "公司": "company",
    "contact_name": "contact_name",
    "contact name": "contact_name",
    "联系人": "contact_name",
    "contact": "contact_name",
    "name": "contact_name",
    "title": "title",
    "职位": "title",
    "country_region": "country_region",
    "country region": "country_region",
    "地区": "country_region",
    "address": "address",
    "地址": "address",
    "market_bucket": "market_bucket",
    "market bucket": "market_bucket",
    "market": "market_bucket",
    "市场": "market_bucket",
    "channel_type": "channel_type",
    "channel type": "channel_type",
    "渠道": "channel_type",
    "source": "source",
    "来源": "source",
    "known_email": "known_email",
    "known email": "known_email",
    "email": "known_email",
    "邮箱": "known_email",
    "known_phone": "known_phone",
    "known phone": "known_phone",
    "phone": "known_phone",
    "电话": "known_phone",
    "whatsapp": "known_phone",
    "product_interest": "product_interest",
    "product interest": "product_interest",
    "product": "product_interest",
    "兴趣产品": "product_interest",
    "product_raw": "product_raw",
    "product raw": "product_raw",
    "产品原文": "product_raw",
    "product_codes": "product_codes",
    "product codes": "product_codes",
    "internal code": "product_codes",
    "internal codes": "product_codes",
    "internal_code": "product_codes",
    "product code": "product_codes",
    "product_code": "product_codes",
    "product codes list": "product_codes",
    "sku": "product_codes",
    "item no": "product_codes",
    "item no.": "product_codes",
    "item_no": "product_codes",
    "内部编码": "product_codes",
    "产品编码": "product_codes",
    "编码": "product_codes",
    "product_names": "product_names",
    "product names": "product_names",
    "batch product names": "product_names",
    "product_name_list": "product_names",
    "batch_product_names": "product_names",
    "产品名称列表": "product_names",
    "批量产品名称": "product_names",
    "product_name": "product_name",
    "product name": "product_name",
    "品名": "product_name",
    "产品名称": "product_name",
    "产品": "product_name",
    "fragrance_requirement": "fragrance_requirement",
    "fragrance requirement": "fragrance_requirement",
    "scent": "fragrance_requirement",
    "fragrance": "fragrance_requirement",
    "香型": "fragrance_requirement",
    "香味": "fragrance_requirement",
    "参考香": "fragrance_requirement",
    "product_application": "product_application",
    "product application": "product_application",
    "application": "product_application",
    "产品用途": "product_application",
    "use": "product_application",
    "用途": "product_application",
    "应用": "product_application",
    "product_quantity": "product_quantity",
    "product quantity": "product_quantity",
    "quantity": "product_quantity",
    "产品数量": "product_quantity",
    "qty": "product_quantity",
    "order quantity": "product_quantity",
    "采购量": "product_quantity",
    "数量": "product_quantity",
    "product_specification": "product_specification",
    "product specification": "product_specification",
    "specification": "product_specification",
    "产品规格": "product_specification",
    "spec": "product_specification",
    "size": "product_specification",
    "容量": "product_specification",
    "浓度": "product_specification",
    "包装": "product_specification",
    "规格": "product_specification",
    "target_price": "target_price",
    "target price": "target_price",
    "target": "target_price",
    "目标价格": "target_price",
    "price": "target_price",
    "budget": "target_price",
    "目标价": "target_price",
    "目标": "target_price",
    "价格": "target_price",
    "预算": "target_price",
    "other_requirements": "other_requirements",
    "other requirements": "other_requirements",
    "requirement": "other_requirements",
    "requirements": "other_requirements",
    "要求": "other_requirements",
    "其他要求": "other_requirements",
    "icp_score": "icp_score",
    "icp score": "icp_score",
    "score": "icp_score",
    "分数": "icp_score",
    "icp_tier": "icp_tier",
    "icp tier": "icp_tier",
    "tier": "icp_tier",
    "等级": "icp_tier",
    "status": "status",
    "状态": "status",
    "next_action": "next_action",
    "next action": "next_action",
    "下一步": "next_action",
    "created_at": "created_at",
    "created at": "created_at",
    "创建时间": "created_at",
    "updated_at": "updated_at",
    "updated at": "updated_at",
    "更新时间": "updated_at",
}


class ValidationError(ValueError):
    """输入不符合 CRM 数据约束。"""


class NotFoundError(KeyError):
    """指定客户不存在。"""


def _redact_log_value(key: str, value: Any) -> Any:
    """对结构化日志中的上下文递归脱敏。

    日志只保留字段名、计数、类型等诊断信息，不写入邮箱、电话、备注、
    下一步正文或完整 Markdown。即使调用方误传 payload，也不会把正文落盘。
    """

    normalized_key = str(key).strip().lower()
    if normalized_key in SENSITIVE_LOG_KEYS or any(token in normalized_key for token in ("email", "phone", "note", "secret", "token")):
        if isinstance(value, str):
            return f"<redacted:{len(value)}>"
        return "<redacted>"
    if isinstance(value, Mapping):
        return {str(item_key): _redact_log_value(str(item_key), item_value) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_redact_log_value(key, item) for item in value]
    if isinstance(value, str):
        # 诊断文本保留短摘要，但长文本只留长度，避免日志膨胀。
        return value if len(value) <= 240 else f"<truncated:{len(value)}>"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


class StructuredLogger:
    """极小的 JSONL 文件日志器，使用标准库并对写日志失败保持容错。"""

    def __init__(self, log_dir: Path):
        self.log_dir = Path(log_dir)
        self.log_path = self.log_dir / LOG_FILENAME
        self._lock = threading.RLock()

    def log(
        self,
        level: str,
        event: str,
        status: str,
        error_code: str,
        message: str,
        details: Optional[Mapping[str, Any]] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> None:
        entry = {
            "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "level": str(level).upper(),
            "event": event,
            "task_phase": event,
            "status": status,
            "error_code": error_code,
            "message": message,
            "details": _redact_log_value("details", dict(details or {})),
            "context": _redact_log_value("context", dict(context or {})),
        }
        line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
        try:
            with self._lock:
                self.log_dir.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(line)
        except Exception as exc:  # 日志故障不能让客户写入/API 失败路径二次崩溃。
            try:
                print(f"CRM structured log unavailable: {type(exc).__name__}", file=sys.stderr)
            except Exception:
                pass

    def info(self, event: str, status: str, error_code: str, message: str, details: Optional[Mapping[str, Any]] = None, context: Optional[Mapping[str, Any]] = None) -> None:
        self.log("INFO", event, status, error_code, message, details, context)

    def warning(self, event: str, status: str, error_code: str, message: str, details: Optional[Mapping[str, Any]] = None, context: Optional[Mapping[str, Any]] = None) -> None:
        self.log("WARNING", event, status, error_code, message, details, context)

    def error(self, event: str, status: str, error_code: str, message: str, details: Optional[Mapping[str, Any]] = None, context: Optional[Mapping[str, Any]] = None) -> None:
        self.log("ERROR", event, status, error_code, message, details, context)


def _today() -> str:
    return _dt.date.today().isoformat()


def _strip_markup(value: Any) -> str:
    """转成一行适合表格/JSON 的字符串，去掉常见强调标记。"""

    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    return text


def _safe_cell(value: Any) -> str:
    return _strip_markup(value).replace("|", "／")


def _normal_field_name(value: Any) -> str:
    text = _strip_markup(value).strip().lower().replace("-", "_")
    text = re.sub(r"\s+", " ", text)
    return FIELD_ALIASES.get(text, text)


def _normalize_multiline(value: Any) -> str:
    """规范化需要保留换行的字段（目前主要是产品原文）。"""

    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    return text.strip()


def _normalize_multiline_list(value: Any) -> str:
    """规范化按行保存的批量字段，同时保留一行一个项目的结构。"""

    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    # 只去掉整体两侧的横向空格；首尾换行可能代表某一侧缺失，必须保留。
    text = text.strip(" \t")
    if not text:
        return ""
    return "\n".join(line.strip() for line in text.split("\n"))


def is_alibaba_source(source: Any) -> bool:
    """按设计文档把 source 含 alibaba/阿里的客户归入 Alibaba 板块。"""

    text = _strip_markup(source).casefold()
    return "alibaba" in text or "阿里" in text


def channel_for_record(record: Mapping[str, Any]) -> str:
    """返回稳定的 UI 板块标识，不改变原始 source。"""

    return "alibaba" if is_alibaba_source(record.get("source")) else "email"


def normalize_channel(value: Any = None, source: Any = None) -> str:
    """归一化客户端传入的板块；source 中的 Alibaba 关键字优先。"""

    if is_alibaba_source(source):
        return "alibaba"
    text = _strip_markup(value).casefold()
    return "alibaba" if text in {"alibaba", "阿里", "ali"} else "email"


def display_name_for_record(record: Mapping[str, Any]) -> str:
    """给卡片和空 Alibaba 档案提供安全的显示名。"""

    company = _strip_markup(record.get("company"))
    contact = _strip_markup(record.get("contact_name"))
    if channel_for_record(record) == "alibaba":
        if contact:
            return contact
        if company and company != _strip_markup(record.get("client_id")):
            return company
        return "未命名阿里客户"
    if company and company != _strip_markup(record.get("client_id")):
        return company
    if contact:
        return contact
    return company or _strip_markup(record.get("client_id")) or "未命名客户"


def _looks_like_unlabelled_product_code(value: Any) -> bool:
    """无标签编码必须同时包含字母和数字，避免把数量当编码。"""

    text = re.sub(r"\s+", " ", _strip_markup(value)).strip()
    if re.fullmatch(r"\d[\d,.]*(?:\s*)(?:kg|kgs|g|mg|ml|l|pcs|pieces|units|boxes|box|bottles?|箱|瓶|公斤|千克|克|毫升|升|件|个)", text, re.IGNORECASE):
        return False
    if re.search(r"\b(?:product|internal|code|name|sku|item)\b", text, re.IGNORECASE):
        return False
    compact = text.replace(" ", "")
    return bool(compact and re.fullmatch(r"(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9._/-]+", compact))


def _clean_tabular_product_name(value: Any) -> str:
    """移除表格状态列，不把 ✅/⚠️ 与其说明混入产品名称。"""

    text = _strip_markup(value).strip(" \t|/:：-—")
    return re.split(r"\s*(?:✅|⚠️|⚠|❌|☑️|✔️)", text, maxsplit=1)[0].strip()


def _clean_tabular_product_code(value: Any) -> str:
    """提取表格编码的主值，忽略编码后的全角/半角括号说明。"""

    text = re.sub(r"\s+", " ", _strip_markup(value)).strip(" \t|/:：-—")
    return re.split(r"\s*[（(]", text, maxsplit=1)[0].strip()


def _tabular_product_pair(line: str) -> Optional[Tuple[str, str]]:
    """解析 Alibaba 常见的 ``序号  名称  编码  状态`` 表格行。

    列可以由 Tab 或至少两个空格分隔；编码内部的单个空格会保留，
    例如 ``FY01 4866E``。同时兼容旧的 ``编码  名称`` 顺序。
    """

    candidate = line.strip()
    if not candidate:
        return None
    numbered = re.match(r"^\s*\d{1,3}(?:[.)、]\s*|\t+| {2,})(?P<body>.+)$", candidate)
    is_numbered = numbered is not None
    if numbered:
        candidate = numbered.group("body").strip()
    columns = [part.strip() for part in re.split(r"\t+| {2,}", candidate) if part.strip()]
    if len(columns) < 2:
        return None
    code_indexes = [
        index
        for index, value in enumerate(columns)
        if _looks_like_unlabelled_product_code(_clean_tabular_product_code(value))
    ]
    if not code_indexes:
        return None
    # Alibaba 导出的带序号表格采用“名称在前、编码在后”。当产品名本身
    # 含年份/型号（例如 Aroma Blend 01）时，两列都可能像编码；此时选
    # 最后一个候选，避免把含数字的产品名误放进编码列。无序号的旧格式
    # 仍优先使用第一个候选，以兼容 ``CODE  Product name``。
    code_index = code_indexes[-1] if is_numbered else code_indexes[0]
    code = _clean_tabular_product_code(columns[code_index])
    if code_index == 0:
        name_parts = columns[1:]
    else:
        name_parts = columns[:code_index]
    name = _clean_tabular_product_name(" ".join(name_parts))
    if not name:
        return None
    return code, name


def _split_bulk_event_values(value: Any, kind: str, *, explicit_label: bool) -> List[str]:
    """把一个编码/名称标签值拆为保序的一行列表。"""

    text = _normalize_multiline(value)
    if not text:
        return []
    values: List[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if kind == "code":
            parts = re.split(r"[,，;；|/\t]+", line)
        else:
            # 批量名称常以逗号/分号列出；显式 Name/Product name 标签
            # 已经把正文边界切开，因此这里按常见批量分隔符拆开。
            parts = re.split(r"[,，;；|/\t]+", line)
        for part in parts:
            candidate = part.strip(" \t,，;；|/")
            if not candidate:
                continue
            if kind == "code" and not explicit_label and not _looks_like_unlabelled_product_code(candidate):
                continue
            values.append(candidate)
    return values


def _line_contains_unlabelled_product_pair(line: str) -> bool:
    """判断一行是否已经是独立的 ``编码 + 名称`` 批量记录。"""

    if _tabular_product_pair(line):
        return True
    for chunk in re.split(r"\s*[;；]\s*", line):
        candidate = chunk.strip()
        if not candidate:
            continue
        split = re.split(r"\s*(?:\||/|\t|,|，|:|：)\s*", candidate, maxsplit=1)
        if len(split) != 2:
            split = re.split(r"\s+", candidate, maxsplit=1)
        if len(split) == 2 and _looks_like_unlabelled_product_code(split[0]) and split[1].strip():
            return True
    return False


def _trim_bulk_value_at_unlabelled_pair(value: str) -> str:
    """不让显式标签吞掉同一行后续的无标签 ``code | name`` 记录。"""

    kept: List[str] = []
    for line in value.splitlines():
        for fragment in re.split(r"[;；]", line):
            fragment = fragment.strip()
            if kept and _line_contains_unlabelled_product_pair(fragment):
                return "\n".join(kept).strip(" \t\r\n,，;；|/")
            if fragment:
                kept.append(fragment)
    return "\n".join(kept).strip(" \t\r\n,，;；|/")


def _bulk_label_events(raw: str) -> List[Tuple[str, int, str]]:
    """提取带标签的编码/名称事件，返回 (kind, start, value)。"""

    label_pairs = [(label, "code") for label in BULK_PRODUCT_CODE_LABELS]
    label_pairs.extend((label, "name") for label in BULK_PRODUCT_NAME_LABELS)
    label_pairs.sort(key=lambda item: len(item[0]), reverse=True)
    pattern = re.compile("|".join(re.escape(label) for label, _ in label_pairs), re.IGNORECASE)
    lookup = {label.casefold(): kind for label, kind in label_pairs}
    separators = set("\n\r,，;；|/\t:：=")
    matches: List[Tuple[str, int, int]] = []
    for match in pattern.finditer(raw):
        kind = lookup.get(match.group(0).casefold())
        if not kind:
            continue
        prefix = raw[: match.start()].rstrip(" \t")
        if prefix and prefix[-1] not in separators:
            # 只接受行首/明确分隔符后的标签，避免正文普通单词误切。
            continue
        suffix = raw[match.end() :]
        delimiter = re.match(r"\s*(?::|：|=|[-—])\s*", suffix)
        if delimiter:
            value_start = match.end() + delimiter.end()
        else:
            space = re.match(r"[ \t]+", suffix)
            if not space:
                continue
            value_start = match.end() + space.end()
        matches.append((kind, value_start, match.start()))

    events: List[Tuple[str, int, str]] = []
    for index, (kind, value_start, label_start) in enumerate(matches):
        value_end = matches[index + 1][2] if index + 1 < len(matches) else len(raw)
        value = raw[value_start:value_end].strip(" \t\r\n,，;；|/")
        # 一个带标签值后的下一行若已经是独立的无标签产品行，不能被
        # 前一个 Name/Code 标签吞掉；其内容会由无标签行解析保序处理。
        value = _trim_bulk_value_at_unlabelled_pair(value)
        if value:
            events.append((kind, label_start, value))
    return events


def _unlabelled_product_pairs(raw: str) -> List[Tuple[int, str, str]]:
    """解析名称/编码表格行及 ``SL-001 | Rose`` 等无标签格式。"""

    pairs: List[Tuple[int, str, str]] = []
    for line_match in re.finditer(r"[^\r\n]+", raw):
        line = line_match.group(0).strip()
        if not line:
            continue
        tabular_pair = _tabular_product_pair(line)
        if tabular_pair:
            code, name = tabular_pair
            pairs.append((line_match.start(), code, name))
            continue
        # 分号切开的片段也可作为一条无标签记录；带竖线/Tab/逗号/冒号
        # 的标准格式优先，名称本身的空格不受影响。
        chunks = re.split(r"\s*[;；]\s*", line)
        offset = line_match.start()
        for chunk in chunks:
            candidate = chunk.strip()
            if not candidate:
                offset += len(chunk) + 1
                continue
            split = re.split(r"\s*(?:\||/|\t|,|，|:|：)\s*", candidate, maxsplit=1)
            if len(split) != 2:
                split = re.split(r"\s+", candidate, maxsplit=1)
            if len(split) != 2:
                if _looks_like_unlabelled_product_code(candidate):
                    pairs.append((offset, candidate, ""))
                offset += len(chunk) + 1
                continue
            code, name = (part.strip() for part in split)
            if _looks_like_unlabelled_product_code(code) and (name or re.search(r"\||/|\t|,|，|:|：", candidate)):
                pairs.append((offset, code, name.strip(" \t|/:：-—")))
            offset += len(chunk) + 1
    return pairs


def _product_items_from_columns(codes: Any, names: Any) -> List[Dict[str, str]]:
    """按行合并编码/名称两列，缺失的一侧保留为空并去重。"""

    normalized_codes = _normalize_multiline_list(codes)
    normalized_names = _normalize_multiline_list(names)
    code_lines = normalized_codes.split("\n") if normalized_codes else []
    name_lines = normalized_names.split("\n") if normalized_names else []
    items: List[Dict[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    for index in range(max(len(code_lines), len(name_lines))):
        code = code_lines[index].strip() if index < len(code_lines) else ""
        name = name_lines[index].strip() if index < len(name_lines) else ""
        if not code and not name:
            continue
        pair = (code, name)
        if pair in seen:
            continue
        seen.add(pair)
        items.append({"code": code, "name": name})
    return items


def _parse_bulk_product_items(raw: str) -> List[Dict[str, str]]:
    """生成带顺序的批量产品项目；解析失败时返回空列表。"""

    events = _bulk_label_events(raw)
    code_values: List[Tuple[str, int]] = []
    name_values: List[Tuple[str, int]] = []
    for kind, start, value in events:
        for item in _split_bulk_event_values(value, kind, explicit_label=True):
            (code_values if kind == "code" else name_values).append((item, start))

    candidates: List[Tuple[int, str, str]] = []
    for index in range(max(len(code_values), len(name_values))):
        code, code_start = code_values[index] if index < len(code_values) else ("", 10**12)
        name, name_start = name_values[index] if index < len(name_values) else ("", 10**12)
        candidates.append((min(code_start, name_start), code, name))
    candidates.extend(_unlabelled_product_pairs(raw))
    candidates.sort(key=lambda item: item[0])

    items: List[Dict[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    for _start, code, name in candidates:
        pair = (code.strip(), name.strip())
        if not pair[0] and not pair[1]:
            continue
        if pair in seen:
            continue
        seen.add(pair)
        items.append({"code": pair[0], "name": pair[1]})
    return items


def _bulk_columns_from_items(items: Sequence[Mapping[str, Any]]) -> Tuple[str, str]:
    return ("\n".join(_strip_markup(item.get("code")) for item in items), "\n".join(_strip_markup(item.get("name")) for item in items))


def parse_product_info(raw_text: Any) -> Dict[str, Any]:
    """把客户产品原文拆成可编辑建议字段。

    该函数是纯函数，方便单元测试和前端 API 共用。标签解析支持中英文、
    ``:``/``：``/``=``/短横线分隔，以及同一行用逗号或分号连接的键值；
    无标签时再补充数量、价格与常见用途启发式。
    """

    raw = _normalize_multiline(raw_text)
    result = {field: "" for field in PRODUCT_FIELDS if field != "product_raw"}
    result["product_items"] = []
    if not raw:
        return result

    label_pairs = [(label, field) for field, labels in PRODUCT_LABELS.items() for label in labels]
    label_pairs.sort(key=lambda item: len(item[0]), reverse=True)
    label_pattern = re.compile("|".join(re.escape(label) for label, _ in label_pairs), re.IGNORECASE)
    label_lookup = {label.casefold(): field for label, field in label_pairs}
    matches: List[Tuple[str, int, int]] = []
    separators = set("\n\r,，;；|/")
    for match in label_pattern.finditer(raw):
        label = match.group(0).casefold()
        field = label_lookup.get(label)
        if not field:
            continue
        # 只忽略标签前的横向空格，不能把换行这一合法分隔符一并去掉。
        prefix = raw[: match.start()].rstrip(" \t")
        if prefix and prefix[-1] not in separators:
            # 标签必须在文本开头或明确分隔符后，避免正文中普通单词
            # （例如 “for product testing”）被误切成字段。
            continue
        suffix = raw[match.end() :]
        delimiter = re.match(r"\s*(?::|：|=|[-—])\s*", suffix)
        if delimiter:
            value_start = match.end() + delimiter.end()
        else:
            # Alibaba 询盘常写成 “Product perfume oil / Qty 25kg”。
            # 无冒号时要求标签和值之间确实有空格，且上面的边界检查
            # 已保证它只出现在开头或分隔符后。
            space = re.match(r"[ \t]+", suffix)
            if not space:
                continue
            value_start = match.end() + space.end()
        matches.append((field, value_start, match.start()))

    for index, (field, value_start, _label_start) in enumerate(matches):
        value_end = matches[index + 1][2] if index + 1 < len(matches) else len(raw)
        value = raw[value_start:value_end].strip(" \t\r\n,，;；|/")
        if not value:
            continue
        if result[field]:
            result[field] = f"{result[field]}；{value}"
        else:
            result[field] = value

    # 标签前的第一段通常就是产品名，例如 “Lavender soap fragrance,
    # 100 kg, for soap”。仅在没有明确品名时使用，避免覆盖手工输入。
    if not result["product_name"]:
        first_segment = re.split(r"[\n,，;；]", raw, maxsplit=1)[0].strip(" \t:-—")
        if (
            first_segment
            and len(first_segment) <= 180
            and not re.search(r"\d+\s*(?:kg|g|ml|l|pcs|件|箱|瓶|公斤|千克|克|毫升)", first_segment, re.IGNORECASE)
            and not re.search(r"(?:USD|US\$|EUR|RMB|CNY|元|€|\$)\s*\d|\d\s*(?:USD|EUR|RMB|CNY|元)", first_segment, re.IGNORECASE)
        ):
            result["product_name"] = first_segment

    quantity_match = re.search(
        r"(?<![\w.])\d[\d,]*(?:\.\d+)?\s*(?:kg|kgs|g|mg|ml|l|pcs|pieces|units|boxes|box|bottles?|箱|瓶|公斤|千克|克|毫升|升|件|个)",
        raw,
        re.IGNORECASE,
    )
    if not result["product_quantity"] and quantity_match:
        result["product_quantity"] = quantity_match.group(0).strip()

    price_match = re.search(
        r"(?:USD|US\$|EUR|RMB|CNY|HKD|€|\$|元)\s*[\d,]+(?:\.\d+)?(?:\s*/\s*[A-Za-z]+)?|[\d,]+(?:\.\d+)?\s*(?:USD|EUR|RMB|CNY|HKD|元)(?:\s*/\s*[A-Za-z]+)?",
        raw,
        re.IGNORECASE,
    )
    if not result["target_price"] and price_match:
        result["target_price"] = price_match.group(0).strip()

    use_tokens = (
        "room spray",
        "room mist",
        "body wash",
        "shower gel",
        "diffuser",
        "perfume",
        "fragrance oil",
        "soap",
        "candle",
        "香水",
        "香皂",
        "肥皂",
        "沐浴露",
        "洗发水",
        "蜡烛",
        "扩香",
        "喷雾",
    )
    use_hits: List[str] = []
    raw_lower = raw.casefold()
    for token in use_tokens:
        if token.casefold() in raw_lower and token not in use_hits:
            use_hits.append(token)
    if not result["product_application"] and use_hits:
        result["product_application"] = "、".join(use_hits)

    # 批量产品信息与旧的单值摘要并存：前者保留顺序和空缺侧，后者只取
    # 第一项名称，避免十余项产品被拼成一个超长 product_name。
    product_items = _parse_bulk_product_items(raw)
    product_codes, product_names = _bulk_columns_from_items(product_items)
    result["product_codes"] = product_codes
    result["product_names"] = product_names
    result["product_items"] = product_items
    first_name = next((item["name"] for item in product_items if item.get("name")), "")
    if product_items:
        # 一旦识别到批量结构，旧单值摘要只反映第一项名称；编码-only
        # 输入则明确保持为空，不把 ``Internal code: ...`` 当产品名称。
        result["product_name"] = first_name
    return result


def product_interest_summary(record: Mapping[str, Any]) -> str:
    """由拆分字段生成简短 product_interest，兼容旧搜索/卡片。"""

    parts = []
    for field in ("product_name", "product_application", "fragrance_requirement"):
        value = _strip_markup(record.get(field))
        if value and value not in parts:
            parts.append(value)
    if parts:
        return " / ".join(parts)[:600]
    return _strip_markup(record.get("product_interest"))[:600]


def _table_row(line: str) -> Optional[List[str]]:
    """解析 Markdown 表格行，允许值中出现额外的 ``|``。"""

    if not line.lstrip().startswith("|"):
        return None
    parts = line.strip().split("|")
    if len(parts) < 3:
        return None
    # 首尾是 split 后的空字符串；中间剩余列保留，调用方按字段数取值。
    return [part.strip() for part in parts[1:-1]]


def _is_separator_row(row: Sequence[str]) -> bool:
    return bool(row) and all(re.fullmatch(r"\s*:?-{3,}:?\s*", cell or "") for cell in row)


def _iter_tables(text: str) -> Iterable[Tuple[int, List[str], List[Tuple[int, List[str]]]]]:
    """逐个产出 Markdown 表格的表头与数据行及其原始行号。"""

    lines = text.splitlines()
    index = 0
    while index < len(lines) - 1:
        header = _table_row(lines[index])
        separator = _table_row(lines[index + 1])
        if header and separator and _is_separator_row(separator):
            rows: List[Tuple[int, List[str]]] = []
            cursor = index + 2
            while cursor < len(lines):
                row = _table_row(lines[cursor])
                if not row or _is_separator_row(row):
                    break
                rows.append((cursor, row))
                cursor += 1
            yield index, header, rows
            index = cursor
        else:
            index += 1


def _section_bounds(text: str, heading: str) -> Optional[Tuple[int, int]]:
    """返回指定二级标题正文的字符边界（不含标题）。"""

    # 兼容已有档案在标题后附加日期/重估说明，例如
    # ``## ICP Rationale（2026-08-22 重估）``。
    match = re.search(r"(?m)^##\s+" + re.escape(heading) + r"(?:\s*[（(].*)?\s*$", text)
    if not match:
        return None
    body_start = match.end()
    next_heading = re.search(r"(?m)^##\s+", text[body_start:])
    body_end = body_start + next_heading.start() if next_heading else len(text)
    return body_start, body_end


def _section_text(text: str, heading: str) -> str:
    bounds = _section_bounds(text, heading)
    if not bounds:
        return ""
    return text[bounds[0] : bounds[1]].strip()


def parse_profile(content: str, fallback_id: str = "") -> Dict[str, Any]:
    """解析单个客户 Markdown 档案。

    既兼容模板中的 ``## Profile`` 表格，也兼容已有档案使用的顶层
    ``| field | value |`` 表格。无详情文件的字段由合并层补齐。
    """

    result: Dict[str, Any] = {field: "" for field in PROFILE_FIELDS}
    result.update(
        {
            "raw_markdown": content,
            "notes": _section_text(content, "Notes"),
            "public_summary": _section_text(content, "Public Summary"),
            "icp_rationale": _section_text(content, "ICP Rationale"),
            "outreach_log": _section_text(content, "Outreach Log"),
            "communication_points": _section_text(content, "Communication Points"),
            "product_quote_links": _section_text(content, "Product / Quote Links"),
        }
    )

    for _, header, rows in _iter_tables(content):
        if len(header) < 2:
            continue
        for _, row in rows:
            if len(row) < 2:
                continue
            key = _normal_field_name(row[0])
            if key not in PROFILE_FIELDS:
                continue
            # 只取第二列，兼容 value 中意外含有 | 的旧记录。
            value = " | ".join(row[1:]).strip()
            if value and not result.get(key):
                result[key] = value

    for multiline_field in ("address", "product_raw", "product_codes", "product_names"):
        if result.get(multiline_field):
            normalizer = _normalize_multiline_list if multiline_field in {"product_codes", "product_names"} else _normalize_multiline
            result[multiline_field] = normalizer(result[multiline_field])

    # 标题仅作为缺失字段的弱回退，不覆盖档案表格中的正式值。
    heading_match = re.search(r"(?m)^#\s+(.+?)\s*$", content)
    if heading_match:
        heading = _strip_markup(heading_match.group(1))
        if " — " in heading:
            company, contact = heading.split(" — ", 1)
            if not result["company"]:
                result["company"] = company.strip()
            if not result["contact_name"] and contact.strip() not in {"(Contact TBD)", "(待确认)", "(待确认联系人)"}:
                result["contact_name"] = contact.strip()
        elif not result["company"]:
            result["company"] = heading

    if not result["client_id"]:
        result["client_id"] = fallback_id
    result["client_id"] = _strip_markup(result["client_id"])
    result["icp_score"] = _parse_score(result.get("icp_score"))
    result["icp_tier"] = _normal_tier(result.get("icp_tier"))
    result["status"] = _normal_status(result.get("status"))
    result["product_items"] = _product_items_from_columns(result.get("product_codes"), result.get("product_names"))
    if result["product_items"] and not result.get("product_name"):
        result["product_name"] = next((item["name"] for item in result["product_items"] if item.get("name")), "")
    return result


def _parse_score(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    try:
        number = int(float(match.group(0)))
    except ValueError:
        return None
    return max(0, min(100, number))


def _normal_tier(value: Any) -> str:
    text = _strip_markup(value).upper()
    match = re.search(r"\b([ABC])\b", text)
    return match.group(1) if match else ""


def _normal_status(value: Any) -> str:
    text = _strip_markup(value).lower().strip()
    text = text.replace(" ", "_")
    # 档案里可能有括号补充说明，状态本体仍可识别。
    for status in KNOWN_STATUSES:
        if re.fullmatch(re.escape(status) + r"(?:[_(（].*)?", text):
            return status
    return text


def parse_index(content: str) -> Dict[str, Dict[str, Any]]:
    """解析客户索引，跳过说明段落及占位行。"""

    result: Dict[str, Dict[str, Any]] = {}
    for _, header, rows in _iter_tables(content):
        names = [_normal_field_name(value) for value in header]
        if not names or names[0] != "client_id":
            continue
        for _, row in rows:
            cells = row + [""] * max(0, len(names) - len(row))
            client_id = _strip_markup(cells[0])
            if not client_id or client_id in {"—", "-"}:
                continue
            values = {names[i]: cells[i].strip() for i in range(min(len(names), len(cells)))}
            result[client_id] = {
                "client_id": client_id,
                "company": values.get("company", ""),
                "market_bucket": values.get("market_bucket", values.get("market", "")),
                "icp_tier": _normal_tier(values.get("icp_tier", values.get("tier", ""))),
                "icp_score": _parse_score(values.get("icp_score", values.get("score", ""))),
                "status": _normal_status(values.get("status", "")),
                "source": values.get("source", ""),
                "updated_at": values.get("updated", values.get("updated_at", "")),
            }
    return result


def parse_pipeline(content: str) -> Dict[str, Dict[str, Any]]:
    """解析 pipeline 中所有分级表格；后出现的同 ID 行视为最新。"""

    result: Dict[str, Dict[str, Any]] = {}
    for _, header, rows in _iter_tables(content):
        names = [_normal_field_name(value) for value in header]
        if not names or names[0] != "client_id":
            continue
        for _, row in rows:
            cells = row + [""] * max(0, len(names) - len(row))
            client_id = _strip_markup(cells[0])
            if not client_id or client_id in {"—", "-"}:
                continue
            values = {names[i]: cells[i].strip() for i in range(min(len(names), len(cells)))}
            result[client_id] = {
                "client_id": client_id,
                "company": values.get("company", ""),
                "market_bucket": values.get("market_bucket", values.get("market", "")),
                "status": _normal_status(values.get("status", "")),
                "next_action": values.get("next_action", ""),
                "updated_at": values.get("updated", values.get("updated_at", "")),
            }
    return result


def _empty_record(client_id: str = "") -> Dict[str, Any]:
    record = {field: "" for field in PROFILE_FIELDS}
    record.update(
        {
            "client_id": client_id,
            "notes": "",
            "raw_markdown": "",
            "public_summary": "",
            "icp_rationale": "",
            "outreach_log": "",
            "communication_points": "",
            "product_quote_links": "",
            "product_items": [],
            "source_file": "",
            "has_profile": False,
        }
    )
    return record


def merge_records(
    index_records: Mapping[str, Mapping[str, Any]],
    pipeline_records: Mapping[str, Mapping[str, Any]],
    profile_records: Mapping[str, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """按 client_id 合并三处数据。

    档案是详细信息主源，索引只补齐缺失字段；pipeline 的状态、下一步行动和
    更新时间代表当前跟进面，最后覆盖对应值。
    """

    all_ids = set(index_records) | set(pipeline_records) | set(profile_records)
    merged: List[Dict[str, Any]] = []
    for client_id in all_ids:
        record = _empty_record(client_id)
        index = index_records.get(client_id, {})
        pipeline = pipeline_records.get(client_id, {})
        profile = profile_records.get(client_id, {})
        # 索引先建立基础，再用有值的档案字段覆盖。
        for source in (index, profile):
            for key, value in source.items():
                if key in record and value not in (None, ""):
                    record[key] = value
        # pipeline 明确提供最新跟进状态字段。
        for key in ("status", "next_action", "updated_at"):
            value = pipeline.get(key, "")
            if value not in (None, ""):
                record[key] = value
        record["client_id"] = client_id
        record["icp_score"] = _parse_score(record.get("icp_score"))
        record["icp_tier"] = _normal_tier(record.get("icp_tier"))
        record["status"] = _normal_status(record.get("status"))
        record["source_file"] = profile.get("source_file", "")
        record["has_profile"] = bool(profile)
        if not record.get("company") and not is_alibaba_source(record.get("source")):
            record["company"] = client_id
        if record.get("product_raw"):
            suggestions = parse_product_info(record["product_raw"])
            for field, value in suggestions.items():
                if field in PRODUCT_FIELDS and field != "product_raw" and not record.get(field):
                    record[field] = value
        record["product_items"] = _product_items_from_columns(record.get("product_codes"), record.get("product_names"))
        if record["product_items"] and not record.get("product_name"):
            record["product_name"] = next((item["name"] for item in record["product_items"] if item.get("name")), "")
        if not record.get("product_interest"):
            record["product_interest"] = product_interest_summary(record)
        record["customer_channel"] = channel_for_record(record)
        record["channel"] = record["customer_channel"]
        record["is_alibaba"] = record["customer_channel"] == "alibaba"
        record["display_name"] = display_name_for_record(record)
        merged.append(record)
    merged.sort(key=lambda item: (_strip_markup(item.get("display_name")) or item["client_id"]).casefold())
    return merged


def scan_data(root: Optional[Path] = None, logger: Optional[StructuredLogger] = None) -> List[Dict[str, Any]]:
    """从指定 ai-assistant 根目录扫描并合并所有客户。"""

    root = Path(root) if root else PROJECT_DIR
    clients_dir = root / "clients"
    leads_dir = root / "leads"
    index_path = clients_dir / "_index.md"
    pipeline_path = leads_dir / "pipeline.md"
    try:
        index_text = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
        pipeline_text = pipeline_path.read_text(encoding="utf-8") if pipeline_path.exists() else ""
    except UnicodeDecodeError as exc:
        if logger:
            logger.error("data_load", "error", ERROR_CODES["parse"], "索引或 pipeline 不是有效 UTF-8", {"error_type": type(exc).__name__}, {"root": str(root)})
        raise ValidationError("客户索引或 pipeline 编码无效") from exc
    except OSError as exc:
        if logger:
            logger.error("data_load", "error", ERROR_CODES["load"], "读取客户索引或 pipeline 失败", {"error_type": type(exc).__name__}, {"root": str(root)})
        raise
    index_records = parse_index(index_text)
    pipeline_records = parse_pipeline(pipeline_text)
    profile_records: Dict[str, Dict[str, Any]] = {}
    if clients_dir.exists():
        for path in clients_dir.glob("*.md"):
            if path.name.startswith("_"):
                continue
            try:
                profile = parse_profile(path.read_text(encoding="utf-8"), path.stem)
            except UnicodeDecodeError as exc:
                # 主数据要求 UTF-8；单个异常档案不应让看板整体失效，但应留下诊断。
                if logger:
                    logger.error("data_load", "partial", ERROR_CODES["parse"], "跳过编码异常的客户档案", {"error_type": type(exc).__name__, "file": path.name}, {"root": str(root)})
                continue
            except OSError as exc:
                if logger:
                    logger.error("data_load", "partial", ERROR_CODES["load"], "跳过无法读取的客户档案", {"error_type": type(exc).__name__, "file": path.name}, {"root": str(root)})
                continue
            except Exception as exc:
                if logger:
                    logger.error("data_load", "partial", ERROR_CODES["parse"], "跳过解析失败的客户档案", {"error_type": type(exc).__name__, "file": path.name}, {"root": str(root)})
                continue
            profile["source_file"] = path.name
            profile_records[profile["client_id"] or path.stem] = profile
    return merge_records(index_records, pipeline_records, profile_records)


def _record_for_id(records: Sequence[Mapping[str, Any]], client_id: str) -> Optional[Dict[str, Any]]:
    for record in records:
        if record.get("client_id") == client_id:
            return dict(record)
    return None


def _validate_client_id(value: Any) -> str:
    client_id = _strip_markup(value)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,119}", client_id):
        raise ValidationError("client_id 只能包含字母、数字、点、下划线和短横线（长度 2-120）")
    return client_id


def _validate_text(field: str, value: Any, max_length: int, required: bool = False) -> str:
    text = _strip_markup(value)
    if required and not text:
        raise ValidationError(f"{field} 不能为空")
    if len(text) > max_length:
        raise ValidationError(f"{field} 不能超过 {max_length} 个字符")
    return text


def validate_client_payload(
    payload: Mapping[str, Any],
    *,
    creating: bool = False,
    channel: Optional[str] = None,
) -> Dict[str, Any]:
    """校验并规范化新增/编辑输入，不修改调用方对象。"""

    if not isinstance(payload, Mapping):
        raise ValidationError("请求体必须是 JSON 对象")
    aliases = {
        "email": "known_email",
        "phone": "known_phone",
        "market": "market_bucket",
        "score": "icp_score",
        "tier": "icp_tier",
        "contact": "contact_name",
        "addr": "address",
    }
    if channel is None:
        raw_channel = payload.get("customer_channel", payload.get("channel", "")) if isinstance(payload, Mapping) else ""
        raw_source = payload.get("source", "") if isinstance(payload, Mapping) else ""
        channel = normalize_channel(raw_channel, raw_source)
    else:
        channel = "alibaba" if _strip_markup(channel).casefold() in {"alibaba", "阿里", "ali"} else "email"
    data: Dict[str, Any] = {}
    for raw_key, value in payload.items():
        key = aliases.get(str(raw_key), str(raw_key))
        if key in EDITABLE_FIELDS or key in {"client_id", "created_at", "updated_at"}:
            data[key] = value
    if creating:
        data["company"] = _validate_text("company", data.get("company"), 200, required=channel != "alibaba")
    elif "company" in data:
        data["company"] = _validate_text("company", data["company"], 200, required=channel != "alibaba")
    text_limits = {
        "contact_name": 160,
        "title": 120,
        "country_region": 240,
        "address": 500,
        "market_bucket": 80,
        "channel_type": 80,
        "source": 100,
        "known_email": 320,
        "known_phone": 120,
        "product_interest": 600,
        "product_codes": 12000,
        "product_names": 12000,
        "product_name": 240,
        "fragrance_requirement": 600,
        "product_application": 300,
        "product_quantity": 160,
        "product_specification": 500,
        "target_price": 160,
        "other_requirements": 1200,
        "next_action": 1200,
        "notes": 6000,
    }
    for field, max_length in text_limits.items():
        if field in data:
            if field == "address":
                data[field] = _normalize_multiline(data[field])
                if len(data[field]) > max_length:
                    raise ValidationError(f"{field} 不能超过 {max_length} 个字符")
            elif field in {"product_codes", "product_names"}:
                data[field] = _normalize_multiline_list(data[field])
                if len(data[field]) > max_length:
                    raise ValidationError(f"{field} 不能超过 {max_length} 个字符")
            else:
                data[field] = _validate_text(field, data[field], max_length)
    if "product_raw" in data:
        data["product_raw"] = _normalize_multiline(data["product_raw"])
        if len(data["product_raw"]) > 10000:
            raise ValidationError("product_raw 不能超过 10000 个字符")
    if "known_email" in data and data["known_email"]:
        # 允许档案中已有的“官网 contact form”等文字，但新录入的明确邮箱需合理。
        email = data["known_email"]
        if "@" in email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValidationError("邮箱格式不正确")
    if "icp_score" in data:
        score = _parse_score(data["icp_score"])
        if score is None or not re.fullmatch(r"\d{1,3}", _strip_markup(data["icp_score"])) or not 0 <= score <= 100:
            raise ValidationError("分数必须是 0 到 100 的整数")
        data["icp_score"] = score
    if "icp_tier" in data:
        tier = _normal_tier(data["icp_tier"])
        if tier not in {"A", "B", "C"}:
            raise ValidationError("等级必须是 A、B 或 C")
        data["icp_tier"] = tier
    if "status" in data:
        status = _normal_status(data["status"])
        if status not in KNOWN_STATUSES:
            raise ValidationError("状态不在允许的 pipeline 状态中")
        data["status"] = status
    if "client_id" in data and data["client_id"]:
        data["client_id"] = _validate_client_id(data["client_id"])
    return data


def _slugify_company(company: str) -> str:
    normalized = company.casefold()
    chars: List[str] = []
    for char in normalized:
        if char.isalnum():
            chars.append(char)
        elif not chars or chars[-1] != "_":
            chars.append("_")
    slug = "".join(chars).strip("_")
    return slug[:70] or "new_client"


def _new_id(company: str, existing_ids: Iterable[str]) -> str:
    existing = set(existing_ids)
    prefix = f"{_today()}_{_slugify_company(company)}"
    candidate = prefix
    counter = 2
    while candidate in existing:
        candidate = f"{prefix}_{counter}"
        counter += 1
    return candidate


def _profile_table_line(label: str, value: Any) -> str:
    field = _normal_field_name(label)
    if field in {"product_raw", "product_codes", "product_names", "address"}:
        # Markdown 表格单元格不能直接跨行；用 <br> 保留换行，解析时再还原。
        normalizer = _normalize_multiline_list if field in {"product_codes", "product_names"} else _normalize_multiline
        safe = normalizer(value).replace("|", "／").replace("\n", "<br>")
    else:
        safe = _safe_cell(value)
    return f"| {label} | {safe} |"


def render_client_markdown(record: Mapping[str, Any]) -> str:
    """按项目模板生成新客户档案；只用于新建或没有详情文件的记录。"""

    source_channel = normalize_channel(record.get("customer_channel"), record.get("source"))
    company_value = _strip_markup(record.get("company"))
    if not company_value and source_channel == "alibaba":
        company_value = "未命名阿里客户"
    company = _safe_cell(company_value or record.get("client_id") or "New client")
    contact = _safe_cell(record.get("contact_name")) or "(待确认)"
    notes = str(record.get("notes") or "").replace("\r", "").strip()
    if not notes:
        notes = "（暂无备注）"
    summary = str(record.get("public_summary") or "").strip() or "（由 CRM 看板新建，待补充公开摘要）"
    rationale = str(record.get("icp_rationale") or "").strip() or "- 由 CRM 看板录入，待补充 ICP 判断"
    communication = str(record.get("communication_points") or "").strip() or "-"
    links = str(record.get("product_quote_links") or "").strip() or "-"
    lines = [
        f"# {company} — {contact}",
        "",
        "## Profile",
        "",
        "| 字段 | 值 |",
        "|---|---|",
    ]
    labels = {
        "client_id": "client_id",
        "company": "company",
        "contact_name": "contact_name",
        "title": "title",
        "country_region": "country_region",
        "address": "address",
        "market_bucket": "market_bucket",
        "channel_type": "channel_type",
        "source": "source",
        "known_email": "known_email",
        "known_phone": "known_phone",
        "product_interest": "product_interest",
        "product_raw": "product_raw",
        "product_codes": "product_codes",
        "product_names": "product_names",
        "product_name": "product_name",
        "fragrance_requirement": "fragrance_requirement",
        "product_application": "product_application",
        "product_quantity": "product_quantity",
        "product_specification": "product_specification",
        "target_price": "target_price",
        "other_requirements": "other_requirements",
        "icp_score": "icp_score",
        "icp_tier": "icp_tier",
        "status": "status",
        "next_action": "next_action",
        "created_at": "created_at",
        "updated_at": "updated_at",
    }
    for field in PROFILE_FIELDS:
        lines.append(_profile_table_line(labels[field], record.get(field, "")))
    lines.extend(
        [
            "",
            "## Public Summary",
            "",
            summary,
            "",
            "## ICP Rationale",
            "",
            rationale,
            "",
            "## Outreach Log",
            "",
            "| date | channel | template | result |",
            "|---|---|---|---|",
            "| | | | |",
            "",
            "## Notes",
            "",
            notes,
            "",
            "## Communication Points",
            "",
            communication,
            "",
            "## Product / Quote Links",
            "",
            links,
            "",
        ]
    )
    return "\n".join(lines)


def _replace_or_insert_profile_fields(content: str, updates: Mapping[str, Any]) -> str:
    """只更新 profile 表格中的目标字段，保留其他行和沟通记录。"""

    lines = content.splitlines()
    found: set[str] = set()
    for index, line in enumerate(lines):
        row = _table_row(line)
        if not row or len(row) < 2:
            continue
        key = _normal_field_name(row[0])
        if key in updates and key in PROFILE_FIELDS:
            lines[index] = _profile_table_line(row[0], updates[key])
            found.add(key)
    missing = [(key, value) for key, value in updates.items() if key in PROFILE_FIELDS and key not in found]
    if missing:
        # 优先插入 Profile 段末尾；旧档案没有 Profile 标题时插入文档开头的表格后。
        section = _section_bounds("\n".join(lines), "Profile")
        if section:
            current = "\n".join(lines)
            start, end = section
            before = current[:end]
            after = current[end:]
            insert = "\n".join(_profile_table_line(key, value) for key, value in missing)
            separator = "\n" if before.endswith("\n") else "\n\n"
            current = before.rstrip("\n") + "\n" + insert + after
            lines = current.splitlines()
        else:
            # 兼容 brudi 等旧档案：在第一个表格数据行之后插入新字段。
            insert_at: Optional[int] = None
            original_text = "\n".join(lines)
            # 选取第一个包含 profile 字段的表格，避免把缺失字段插入
            # Outreach Log 等后续表格。
            for _, _, table_rows in _iter_tables(original_text):
                profile_rows = [line_no for line_no, row in table_rows if len(row) >= 2 and _normal_field_name(row[0]) in PROFILE_FIELDS]
                if profile_rows:
                    insert_at = max(profile_rows) + 1
                    break
            if insert_at is None:
                for idx, line in enumerate(lines):
                    if _table_row(line) is not None:
                        insert_at = idx + 1
            if insert_at is None:
                insert_at = 0
            lines[insert_at:insert_at] = [_profile_table_line(key, value) for key, value in missing]
    return "\n".join(lines) + ("\n" if content.endswith("\n") else "")


def _replace_notes(content: str, notes: str) -> str:
    notes_text = str(notes or "").replace("\r", "").strip() or "（暂无备注）"
    bounds = _section_bounds(content, "Notes")
    if bounds:
        start, end = bounds
        prefix = content[:start]
        suffix = content[end:]
        # 保留 heading 前的换行和下一个 heading，替换仅限 Notes 正文。
        return prefix.rstrip("\n") + "\n\n" + notes_text + "\n" + suffix.lstrip("\n")
    base = content.rstrip("\n")
    return base + "\n\n## Notes\n\n" + notes_text + "\n"


def _replace_index_row(content: str, record: Mapping[str, Any]) -> str:
    lines = content.splitlines()
    target = str(record["client_id"])
    for _, _, rows in _iter_tables(content):
        for line_number, row in rows:
            if row and _strip_markup(row[0]) == target:
                replacement = [
                    target,
                    _safe_cell(record.get("company")),
                    _safe_cell(record.get("market_bucket")),
                    _safe_cell(record.get("icp_tier")),
                    _safe_cell(record.get("icp_score") if record.get("icp_score") is not None else ""),
                    _safe_cell(record.get("status")),
                    _safe_cell(record.get("source")),
                    _safe_cell(record.get("updated_at")),
                ]
                lines[line_number] = "| " + " | ".join(replacement) + " |"
                return "\n".join(lines) + ("\n" if content.endswith("\n") else "")
    row = "| " + " | ".join(
        [
            target,
            _safe_cell(record.get("company")),
            _safe_cell(record.get("market_bucket")),
            _safe_cell(record.get("icp_tier")),
            _safe_cell(record.get("icp_score") if record.get("icp_score") is not None else ""),
            _safe_cell(record.get("status")),
            _safe_cell(record.get("source")),
            _safe_cell(record.get("updated_at")),
        ]
    ) + " |"
    marker = re.search(r"(?m)^##\s+使用说明\s*$", content)
    if marker:
        return content[: marker.start()].rstrip("\n") + "\n" + row + "\n\n" + content[marker.start() :]
    return content.rstrip("\n") + "\n" + row + "\n"


def _pipeline_section_for_tier(tier: str) -> str:
    return {"A": "A 级优先", "B": "B 级跟进", "C": "C 级 / 待补充"}.get(tier, "B 级跟进")


def _replace_pipeline_row(content: str, record: Mapping[str, Any]) -> str:
    lines = content.splitlines()
    target = str(record["client_id"])
    replacement = [
        target,
        _safe_cell(record.get("company")),
        _safe_cell(record.get("market_bucket") or record.get("country_region")),
        _safe_cell(record.get("status")),
        _safe_cell(record.get("next_action")),
        _safe_cell(record.get("updated_at")),
    ]
    for _, header, rows in _iter_tables(content):
        names = [_normal_field_name(value) for value in header]
        if not names or names[0] != "client_id":
            continue
        for line_number, row in rows:
            if row and _strip_markup(row[0]) == target:
                # pipeline 主表统一 6 列；即使旧表额外带 note，也保留额外列。
                if len(row) > len(replacement):
                    replacement.extend(row[len(replacement) :])
                lines[line_number] = "| " + " | ".join(replacement[: max(len(row), 6)]) + " |"
                return "\n".join(lines) + ("\n" if content.endswith("\n") else "")

    heading = _pipeline_section_for_tier(str(record.get("icp_tier") or "B"))
    heading_match = re.search(r"(?m)^##\s+" + re.escape(heading) + r"\s*$", content)
    row = "| " + " | ".join(replacement) + " |"
    if heading_match:
        body_start = heading_match.end()
        next_heading = re.search(r"(?m)^##\s+", content[body_start:])
        body_end = body_start + next_heading.start() if next_heading else len(content)
        insertion = content[body_start:body_end].rstrip("\n") + "\n" + row + "\n"
        return content[:body_start] + insertion + content[body_end:]
    return content.rstrip("\n") + f"\n\n## {heading}\n\n| client_id | company | market | status | next_action | updated |\n|---|---|---|---|---|---|\n{row}\n"


def _write_utf8(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


class CRMStore:
    """线程安全的数据读写门面，便于服务与测试共用。"""

    def __init__(self, project_dir: Optional[Path] = None):
        self.project_dir = Path(project_dir) if project_dir else PROJECT_DIR
        self.clients_dir = self.project_dir / "clients"
        self.leads_dir = self.project_dir / "leads"
        self.index_path = self.clients_dir / "_index.md"
        self.pipeline_path = self.leads_dir / "pipeline.md"
        self.logger = StructuredLogger(self.project_dir / "crm-dashboard" / "logs")
        self._lock = threading.RLock()

    def list_clients(self) -> List[Dict[str, Any]]:
        with self._lock:
            try:
                records = scan_data(self.project_dir, logger=self.logger)
                self.logger.info("data_load", "success", ERROR_CODES["ok"], "客户数据加载完成", {"client_count": len(records)}, {"root": str(self.project_dir)})
                return records
            except Exception as exc:
                # scan_data 已记录可识别的解析/读取错误；这里补一条统一加载失败事件。
                if isinstance(exc, ValidationError):
                    code = ERROR_CODES["parse"]
                elif isinstance(exc, OSError):
                    code = ERROR_CODES["load"]
                else:
                    code = ERROR_CODES["unexpected"]
                self.logger.error("data_load", "error", code, "客户数据加载失败", {"error_type": type(exc).__name__}, {"root": str(self.project_dir)})
                raise

    def create_client(self, payload: Mapping[str, Any], *, channel: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            payload_keys = sorted(str(key) for key in payload.keys()) if isinstance(payload, Mapping) else []
            self.logger.info("create_client", "started", ERROR_CODES["ok"], "开始创建客户", {"fields": payload_keys}, {"operation": "create"})
            try:
                raw_source = payload.get("source", "") if isinstance(payload, Mapping) else ""
                raw_channel = channel if channel is not None else (payload.get("customer_channel", payload.get("channel", "")) if isinstance(payload, Mapping) else "")
                selected_channel = normalize_channel(raw_channel, raw_source)
                data = validate_client_payload(payload, creating=True, channel=selected_channel)
            except ValidationError as exc:
                self.logger.warning("validation", "rejected", ERROR_CODES["validation"], "创建客户输入校验失败", {"error_type": type(exc).__name__, "fields": payload_keys}, {"operation": "create"})
                raise
            data["source"] = "alibaba" if selected_channel == "alibaba" else "email_manual"
            if data.get("product_raw"):
                suggestions = parse_product_info(data["product_raw"])
                for field, value in suggestions.items():
                    if field in PRODUCT_FIELDS and field != "product_raw" and not data.get(field):
                        data[field] = value
            if (data.get("product_raw") or any(data.get(field) for field in PRODUCT_FIELDS if field != "product_raw")) and not data.get("product_interest"):
                data["product_interest"] = product_interest_summary(data)
            records = self.list_clients()
            existing_ids = [str(item["client_id"]) for item in records]
            id_seed = data.get("company") or data.get("contact_name") or ("unnamed_alibaba" if selected_channel == "alibaba" else "new_client")
            client_id = data.get("client_id") or _new_id(id_seed, existing_ids)
            if client_id in existing_ids or (self.clients_dir / f"{client_id}.md").exists():
                self.logger.warning("validation", "rejected", ERROR_CODES["validation"], "创建客户失败：client_id 已存在", {"error_type": "DuplicateClientId"}, {"operation": "create", "client_id": client_id})
                raise ValidationError("client_id 已存在")
            created = _today()
            record = _empty_record(client_id)
            record.update(data)
            record.update(
                {
                    "client_id": client_id,
                    "created_at": data.get("created_at") or created,
                    "updated_at": data.get("updated_at") or created,
                    "status": data.get("status") or "new",
                    "icp_tier": data.get("icp_tier") or "C",
                    "has_profile": True,
                    "source_file": f"{client_id}.md",
                }
            )
            record["icp_score"] = _parse_score(record.get("icp_score"))
            if record["icp_score"] is None:
                record["icp_score"] = 0
            record["customer_channel"] = selected_channel
            record["channel"] = selected_channel
            record["is_alibaba"] = selected_channel == "alibaba"
            record["product_items"] = _product_items_from_columns(record.get("product_codes"), record.get("product_names"))
            if record["product_items"] and not record.get("product_name"):
                record["product_name"] = next((item["name"] for item in record["product_items"] if item.get("name")), "")
            record["display_name"] = display_name_for_record(record)
            try:
                index_text = self.index_path.read_text(encoding="utf-8") if self.index_path.exists() else "# 客户索引\n\n| client_id | company | market_bucket | tier | score | status | source | updated |\n|---|---|---|---|---|---|---|---|\n"
                pipeline_text = self.pipeline_path.read_text(encoding="utf-8") if self.pipeline_path.exists() else "# Lead Pipeline\n"
            except UnicodeDecodeError as exc:
                self.logger.error("create_client", "error", ERROR_CODES["parse"], "创建客户前读取索引/pipeline 编码失败", {"error_type": type(exc).__name__}, {"operation": "create", "client_id": client_id})
                raise ValidationError("客户索引或 pipeline 编码无效") from exc
            except OSError as exc:
                self.logger.error("create_client", "error", ERROR_CODES["load"], "创建客户前读取索引/pipeline 失败", {"error_type": type(exc).__name__}, {"operation": "create", "client_id": client_id})
                raise
            try:
                _write_utf8(self.clients_dir / f"{client_id}.md", render_client_markdown(record))
                _write_utf8(self.index_path, _replace_index_row(index_text, record))
                _write_utf8(self.pipeline_path, _replace_pipeline_row(pipeline_text, record))
            except OSError as exc:
                self.logger.error("file_write", "error", ERROR_CODES["write"], "创建客户文件写入失败", {"error_type": type(exc).__name__}, {"operation": "create", "client_id": client_id})
                raise
            except Exception as exc:
                self.logger.error("create_client", "error", ERROR_CODES["unexpected"], "创建客户时发生未捕获异常", {"error_type": type(exc).__name__}, {"operation": "create", "client_id": client_id})
                raise
            self.logger.info("create_client", "success", ERROR_CODES["ok"], "客户创建成功", {"client_id": client_id}, {"operation": "create"})
            return record

    def update_client(self, client_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        with self._lock:
            requested_id = _strip_markup(client_id)
            payload_keys = sorted(str(key) for key in payload.keys()) if isinstance(payload, Mapping) else []
            self.logger.info("update_client", "started", ERROR_CODES["ok"], "开始更新客户", {"fields": payload_keys}, {"operation": "update", "client_id": requested_id})
            try:
                client_id = _validate_client_id(client_id)
            except ValidationError as exc:
                self.logger.warning("validation", "rejected", ERROR_CODES["validation"], "更新客户输入校验失败", {"error_type": type(exc).__name__, "fields": payload_keys}, {"operation": "update", "client_id": requested_id})
                raise
            records = self.list_clients()
            record = _record_for_id(records, client_id)
            if record is None:
                self.logger.warning("update_client", "not_found", ERROR_CODES["not_found"], "更新客户失败：客户不存在", {"error_type": "NotFoundError"}, {"operation": "update", "client_id": client_id})
                raise NotFoundError(client_id)
            try:
                raw_source = payload.get("source", record.get("source", "")) if isinstance(payload, Mapping) else record.get("source", "")
                raw_channel = payload.get("customer_channel", payload.get("channel", "")) if isinstance(payload, Mapping) else ""
                selected_channel = normalize_channel(raw_channel or channel_for_record(record), raw_source)
                data = validate_client_payload(payload, creating=False, channel=selected_channel)
            except ValidationError as exc:
                self.logger.warning("validation", "rejected", ERROR_CODES["validation"], "更新客户输入校验失败", {"error_type": type(exc).__name__, "fields": payload_keys}, {"operation": "update", "client_id": client_id})
                raise
            merged = dict(record)
            merged.update(data)
            merged["client_id"] = client_id
            merged["updated_at"] = _today()
            merged["status"] = _normal_status(merged.get("status")) or "new"
            if merged["status"] not in KNOWN_STATUSES:
                self.logger.warning("validation", "rejected", ERROR_CODES["validation"], "更新客户失败：状态无效", {"error_type": "InvalidStatus"}, {"operation": "update", "client_id": client_id})
                raise ValidationError("状态不在允许的 pipeline 状态中")
            merged["icp_tier"] = _normal_tier(merged.get("icp_tier")) or "C"
            if merged.get("product_raw"):
                suggestions = parse_product_info(merged["product_raw"])
                for field, value in suggestions.items():
                    if field not in PRODUCT_FIELDS or field == "product_raw" or field in data:
                        continue
                    # API 只更新 product_raw 时，未随请求提供的拆分字段
                    # 视为自动字段，允许随第二次原文更新刷新；前端若
                    # 用户手改，会把该字段一并提交，因此仍保持不覆盖。
                    if "product_raw" in data or not merged.get(field):
                        merged[field] = value
            merged["product_items"] = _product_items_from_columns(merged.get("product_codes"), merged.get("product_names"))
            if merged["product_items"] and "product_name" not in data and not merged.get("product_name"):
                merged["product_name"] = next((item["name"] for item in merged["product_items"] if item.get("name")), "")
            if "product_interest" not in data and any(merged.get(field) for field in PRODUCT_FIELDS if field != "product_raw"):
                merged["product_interest"] = product_interest_summary(merged)
            merged["customer_channel"] = channel_for_record(merged)
            merged["channel"] = merged["customer_channel"]
            merged["is_alibaba"] = merged["customer_channel"] == "alibaba"
            merged["display_name"] = display_name_for_record(merged)
            profile_path = self.clients_dir / f"{client_id}.md"
            try:
                if profile_path.exists():
                    original = profile_path.read_text(encoding="utf-8")
                    profile_updates = {key: merged.get(key, "") for key in data if key in PROFILE_FIELDS}
                    if "product_raw" in data or any(field in data for field in PRODUCT_FIELDS):
                        for field in PRODUCT_FIELDS:
                            profile_updates[field] = merged.get(field, "")
                        profile_updates["product_interest"] = merged.get("product_interest", "")
                    profile_updates["updated_at"] = merged["updated_at"]
                    updated_text = _replace_or_insert_profile_fields(original, profile_updates)
                    if "notes" in data:
                        updated_text = _replace_notes(updated_text, merged.get("notes", ""))
                    _write_utf8(profile_path, updated_text)
                    merged["raw_markdown"] = updated_text
                else:
                    # 索引/pipeline-only 客户首次编辑时补齐一份详情档案。
                    merged["source_file"] = profile_path.name
                    merged["has_profile"] = True
                    merged["raw_markdown"] = render_client_markdown(merged)
                    _write_utf8(profile_path, merged["raw_markdown"])
                index_text = self.index_path.read_text(encoding="utf-8") if self.index_path.exists() else ""
                pipeline_text = self.pipeline_path.read_text(encoding="utf-8") if self.pipeline_path.exists() else ""
            except UnicodeDecodeError as exc:
                self.logger.error("update_client", "error", ERROR_CODES["parse"], "更新客户前读取档案/索引编码失败", {"error_type": type(exc).__name__}, {"operation": "update", "client_id": client_id})
                raise ValidationError("客户档案、索引或 pipeline 编码无效") from exc
            except OSError as exc:
                self.logger.error("file_write", "error", ERROR_CODES["write"], "更新客户文件写入失败", {"error_type": type(exc).__name__}, {"operation": "update", "client_id": client_id})
                raise
            try:
                if index_text:
                    _write_utf8(self.index_path, _replace_index_row(index_text, merged))
                if pipeline_text:
                    _write_utf8(self.pipeline_path, _replace_pipeline_row(pipeline_text, merged))
            except OSError as exc:
                self.logger.error("file_write", "error", ERROR_CODES["write"], "更新索引或 pipeline 写入失败", {"error_type": type(exc).__name__}, {"operation": "update", "client_id": client_id})
                raise
            except Exception as exc:
                self.logger.error("update_client", "error", ERROR_CODES["unexpected"], "更新客户时发生未捕获异常", {"error_type": type(exc).__name__}, {"operation": "update", "client_id": client_id})
                raise
            self.logger.info("update_client", "success", ERROR_CODES["ok"], "客户更新成功", {"client_id": client_id}, {"operation": "update"})
            return merged


def _filter_values(records: Sequence[Mapping[str, Any]]) -> Dict[str, List[str]]:
    statuses = sorted({str(item.get("status")) for item in records if item.get("status")}, key=lambda value: (STATUS_ORDER.get(value, 999), value))
    tiers = [tier for tier in ("A", "B", "C") if any(item.get("icp_tier") == tier for item in records)]
    markets = sorted({str(item.get("market_bucket")) for item in records if item.get("market_bucket")}, key=str.casefold)
    sources = sorted({str(item.get("source")) for item in records if item.get("source")}, key=str.casefold)
    return {"statuses": statuses, "tiers": tiers, "markets": markets, "sources": sources}


def response_payload(records: Sequence[Mapping[str, Any]], channel: Optional[str] = None) -> Dict[str, Any]:
    all_records = list(records)
    selected = [item for item in all_records if not channel or channel_for_record(item) == channel]
    channels = {
        "alibaba": sum(1 for item in all_records if channel_for_record(item) == "alibaba"),
        "email": sum(1 for item in all_records if channel_for_record(item) == "email"),
    }
    active = [item for item in selected if str(item.get("status") or "") not in CLOSED_STATUSES]
    pending = [item for item in active if _strip_markup(item.get("next_action"))]
    return {
        "clients": [dict(item) for item in selected],
        "filters": _filter_values(selected),
        "channel": channel or "all",
        "channels": channels,
        "stats": {
            "total": len(selected),
            "tier_a": sum(1 for item in selected if item.get("icp_tier") == "A"),
            "active": len(active),
            "pending": len(pending),
        },
    }


ALIBABA_CSV_COLUMNS: Tuple[Tuple[str, str], ...] = (
    ("ID", "client_id"),
    ("姓名", "contact_name"),
    ("公司", "company"),
    ("地址", "address"),
    ("电话", "known_phone"),
    ("邮箱", "known_email"),
    ("产品原文", "product_raw"),
    ("产品名称", "product_name"),
    ("内部编码", "product_codes"),
    ("批量产品名称", "product_names"),
    ("香型要求", "fragrance_requirement"),
    ("产品用途", "product_application"),
    ("产品数量", "product_quantity"),
    ("产品规格", "product_specification"),
    ("目标价格", "target_price"),
    ("其他要求", "other_requirements"),
    ("备注", "notes"),
)


def alibaba_csv_bytes(records: Sequence[Mapping[str, Any]]) -> bytes:
    """生成带 UTF-8 BOM 的稳定列顺序 Alibaba CSV，便于 Excel 直接打开。"""

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([label for label, _ in ALIBABA_CSV_COLUMNS])
    for record in records:
        if channel_for_record(record) != "alibaba":
            continue
        writer.writerow([_normalize_multiline_list(record.get(field)) if field in {"product_codes", "product_names"} else _normalize_multiline(record.get(field)) if field == "product_raw" else _strip_markup(record.get(field)) for _, field in ALIBABA_CSV_COLUMNS])
    return buffer.getvalue().encode("utf-8-sig")


class CRMRequestHandler(BaseHTTPRequestHandler):
    """JSON API 与静态资源处理器。``store`` 在 server 初始化时注入。"""

    store: CRMStore = CRMStore()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003 - stdlib handler API
        # 本地看板不需要把每次静态资源请求刷满终端。
        return

    def log_request(self, code: Any = "-", size: Any = "-") -> None:  # noqa: N802 - stdlib handler API
        """把每个 HTTP 请求写成一条不含请求正文的结构化事件。"""

        try:
            numeric_code = int(code)
        except (TypeError, ValueError):
            numeric_code = 500
        logger = getattr(self.store, "logger", None)
        if logger:
            logger.info(
                "api_request",
                "success" if numeric_code < 400 else "error",
                ERROR_CODES["ok"] if numeric_code < 400 else ERROR_CODES["api"],
                "API 请求完成",
                {"http_status": numeric_code, "response_bytes": size},
                {"method": self.command, "path": urlsplit(self.path).path},
            )

    def _send_json(self, status: int, payload: Mapping[str, Any]) -> None:
        body_payload = dict(payload)
        if status >= 400 and not body_payload.get("error_code"):
            body_payload["error_code"] = ERROR_CODES["api"]
        body = json.dumps(body_payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, status: int, body: bytes, content_type: str, *, download_name: Optional[str] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "页面资源不存在"})
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or path.suffix in {".js", ".css"}:
            content_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlsplit(self.path)
        if parsed.path == "/api/health":
            try:
                count = len(self.store.list_clients())
                self._send_json(HTTPStatus.OK, {"status": "ok", "service": "crm-dashboard", "clients": count})
            except Exception as exc:
                self.store.logger.error("api_health", "error", ERROR_CODES["api"], "健康检查失败", {"error_type": type(exc).__name__}, {"method": "GET"})
                self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error", "service": "crm-dashboard", "error_code": ERROR_CODES["api"], "error": "服务健康检查失败"})
            return
        if parsed.path == "/api/clients":
            try:
                params = parse_qs(parsed.query)
                requested_channel = params.get("channel", [""])[0].strip().casefold()
                if requested_channel in {"", "all"}:
                    channel = None
                elif requested_channel in {"alibaba", "阿里", "ali"}:
                    channel = "alibaba"
                elif requested_channel in {"email", "邮件"}:
                    channel = "email"
                else:
                    raise ValidationError("channel 只能是 alibaba 或 email")
                self._send_json(HTTPStatus.OK, response_payload(self.store.list_clients(), channel))
            except ValidationError as exc:
                self.store.logger.warning("api_clients", "rejected", ERROR_CODES["validation"], "客户列表接口参数无效", {"error_type": type(exc).__name__}, {"method": "GET"})
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc), "error_code": ERROR_CODES["validation"]})
            except Exception as exc:
                code = ERROR_CODES["parse"] if isinstance(exc, ValidationError) else ERROR_CODES["load"] if isinstance(exc, OSError) else ERROR_CODES["api"]
                self.store.logger.error("api_clients", "error", code, "客户列表接口失败", {"error_type": type(exc).__name__}, {"method": "GET"})
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "读取客户数据失败", "error_code": code})
            return
        if parsed.path in {"/api/clients/export.csv", "/api/clients/export"}:
            try:
                params = parse_qs(parsed.query)
                requested_channel = params.get("channel", ["alibaba"])[0].strip().casefold()
                if requested_channel not in {"alibaba", "阿里", "ali"}:
                    raise ValidationError("CSV 导出仅支持 alibaba 板块")
                body = alibaba_csv_bytes(self.store.list_clients())
                self.store.logger.info("csv_export", "success", ERROR_CODES["ok"], "Alibaba CSV 导出完成", {"byte_count": len(body)}, {"method": "GET", "channel": "alibaba"})
                self._send_bytes(HTTPStatus.OK, body, "text/csv; charset=utf-8", download_name="alibaba-customers.csv")
            except ValidationError as exc:
                self.store.logger.warning("csv_export", "rejected", ERROR_CODES["validation"], "CSV 导出参数无效", {"error_type": type(exc).__name__}, {"method": "GET"})
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc), "error_code": ERROR_CODES["validation"]})
            except Exception as exc:
                code = ERROR_CODES["load"] if isinstance(exc, OSError) else ERROR_CODES["api"]
                self.store.logger.error("csv_export", "error", code, "CSV 导出失败", {"error_type": type(exc).__name__}, {"method": "GET"})
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "CSV 导出失败", "error_code": code})
            return
        if parsed.path.startswith("/api/clients/"):
            client_id = unquote(parsed.path.rsplit("/", 1)[-1])
            try:
                record = _record_for_id(self.store.list_clients(), client_id)
                if record is None:
                    raise NotFoundError(client_id)
                self._send_json(HTTPStatus.OK, record)
            except NotFoundError:
                self.store.logger.warning("api_client_detail", "not_found", ERROR_CODES["not_found"], "详情接口找不到客户", {"error_type": "NotFoundError"}, {"method": "GET", "client_id": client_id})
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "客户不存在", "error_code": ERROR_CODES["not_found"]})
            except ValidationError as exc:
                self.store.logger.warning("api_client_detail", "rejected", ERROR_CODES["validation"], "详情接口参数无效", {"error_type": type(exc).__name__}, {"method": "GET"})
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc), "error_code": ERROR_CODES["validation"]})
            return
        if parsed.path.startswith("/api/"):
            self.store.logger.warning("api_request", "not_found", ERROR_CODES["api"], "API 路径不存在", {"http_status": 404}, {"method": "GET", "path": parsed.path})
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "接口不存在", "error_code": ERROR_CODES["api"]})
            return
        filename = STATIC_FILES.get(parsed.path)
        if filename:
            self._send_file(BASE_DIR / filename)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "页面不存在"})

    def _read_json(self) -> Dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValidationError("请求体长度无效") from exc
        if length <= 0 or length > 1_000_000:
            raise ValidationError("请求体为空或超过 1 MB")
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError("请求体必须是有效 UTF-8 JSON") from exc
        if not isinstance(value, dict):
            raise ValidationError("请求体必须是 JSON 对象")
        return value

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlsplit(self.path)
        if parsed.path == "/api/product-info/parse":
            started = time.perf_counter()
            try:
                payload = self._read_json()
                raw_value = payload.get("raw_text", payload.get("product_raw", ""))
                if raw_value is None:
                    raw_value = ""
                if not isinstance(raw_value, str):
                    raise ValidationError("raw_text 必须是字符串")
                raw = _normalize_multiline(raw_value)
                if len(raw) > 10000:
                    raise ValidationError("产品原文不能超过 10000 个字符")
                fields = parse_product_info(raw)
                duration_ms = round((time.perf_counter() - started) * 1000, 2)
                matched_fields = [field for field, value in fields.items() if field != "product_items" and value]
                item_count = len(fields.get("product_items") or [])
                error_code = ERROR_CODES["bulk_product_parse"] if item_count or fields.get("product_codes") or fields.get("product_names") else ERROR_CODES["product_parse"]
                # 这里明确只记录长度、命中字段、条数和耗时，绝不记录原文。
                self.store.logger.info(
                    "bulk_product_parse" if error_code == ERROR_CODES["bulk_product_parse"] else "product_parse",
                    "success",
                    error_code,
                    "产品信息拆分完成",
                    {"raw_length": len(raw), "matched_fields": matched_fields, "item_count": item_count, "duration_ms": duration_ms},
                    {"method": "POST", "path": "/api/product-info/parse"},
                )
                self._send_json(HTTPStatus.OK, {"fields": fields, "raw_length": len(raw), "matched_fields": matched_fields})
            except ValidationError as exc:
                duration_ms = round((time.perf_counter() - started) * 1000, 2)
                self.store.logger.warning(
                    "product_parse",
                    "rejected",
                    ERROR_CODES["product_parse"],
                    "产品信息拆分输入无效",
                    {"error_type": type(exc).__name__, "duration_ms": duration_ms},
                    {"method": "POST", "path": "/api/product-info/parse"},
                )
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc), "error_code": ERROR_CODES["product_parse"]})
            except Exception as exc:
                duration_ms = round((time.perf_counter() - started) * 1000, 2)
                self.store.logger.error(
                    "product_parse",
                    "error",
                    ERROR_CODES["unexpected"],
                    "产品信息拆分发生未捕获异常",
                    {"error_type": type(exc).__name__, "duration_ms": duration_ms},
                    {"method": "POST", "path": "/api/product-info/parse"},
                )
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "产品信息拆分失败", "error_code": ERROR_CODES["unexpected"]})
            return
        if parsed.path != "/api/clients":
            self.store.logger.warning("api_request", "not_found", ERROR_CODES["api"], "创建接口路径不存在", {"http_status": 404}, {"method": "POST", "path": parsed.path})
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "接口不存在", "error_code": ERROR_CODES["api"]})
            return
        try:
            payload = self._read_json()
            query_channel = parse_qs(parsed.query).get("channel", [""])[0].strip().casefold()
            channel = None if not query_channel else ("alibaba" if query_channel in {"alibaba", "阿里", "ali"} else "email" if query_channel in {"email", "邮件"} else None)
            if query_channel and channel is None:
                raise ValidationError("channel 只能是 alibaba 或 email")
            record = self.store.create_client(payload, channel=channel)
            self._send_json(HTTPStatus.CREATED, {"client": record, "message": "客户已创建"})
        except ValidationError as exc:
            self.store.logger.warning("api_create_client", "rejected", ERROR_CODES["validation"], "创建接口输入校验失败", {"error_type": type(exc).__name__}, {"method": "POST"})
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc), "error_code": ERROR_CODES["validation"]})
        except OSError as exc:
            self.store.logger.error("api_create_client", "error", ERROR_CODES["write"], "创建接口文件写入失败", {"error_type": type(exc).__name__}, {"method": "POST"})
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "客户文件写入失败", "error_code": ERROR_CODES["write"]})
        except Exception as exc:
            self.store.logger.error("api_create_client", "error", ERROR_CODES["unexpected"], "创建接口发生未捕获异常", {"error_type": type(exc).__name__}, {"method": "POST"})
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "创建客户失败", "error_code": ERROR_CODES["unexpected"]})

    def do_PATCH(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlsplit(self.path)
        if not parsed.path.startswith("/api/clients/"):
            self.store.logger.warning("api_request", "not_found", ERROR_CODES["api"], "更新接口路径不存在", {"http_status": 404}, {"method": "PATCH", "path": parsed.path})
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "接口不存在", "error_code": ERROR_CODES["api"]})
            return
        client_id = unquote(parsed.path.rsplit("/", 1)[-1])
        try:
            record = self.store.update_client(client_id, self._read_json())
            self._send_json(HTTPStatus.OK, {"client": record, "message": "客户已更新"})
        except NotFoundError:
            self.store.logger.warning("api_update_client", "not_found", ERROR_CODES["not_found"], "更新接口找不到客户", {"error_type": "NotFoundError"}, {"method": "PATCH", "client_id": client_id})
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "客户不存在", "error_code": ERROR_CODES["not_found"]})
        except ValidationError as exc:
            self.store.logger.warning("api_update_client", "rejected", ERROR_CODES["validation"], "更新接口输入校验失败", {"error_type": type(exc).__name__}, {"method": "PATCH", "client_id": client_id})
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc), "error_code": ERROR_CODES["validation"]})
        except OSError as exc:
            self.store.logger.error("api_update_client", "error", ERROR_CODES["write"], "更新接口文件写入失败", {"error_type": type(exc).__name__}, {"method": "PATCH", "client_id": client_id})
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "客户文件写入失败", "error_code": ERROR_CODES["write"]})
        except Exception as exc:
            self.store.logger.error("api_update_client", "error", ERROR_CODES["unexpected"], "更新接口发生未捕获异常", {"error_type": type(exc).__name__}, {"method": "PATCH", "client_id": client_id})
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "更新客户失败", "error_code": ERROR_CODES["unexpected"]})


def create_server(host: str = "127.0.0.1", port: int = 8765, project_dir: Optional[Path] = None) -> ThreadingHTTPServer:
    """创建可用于测试或运行的 HTTP server。"""

    handler_class = type("BoundCRMRequestHandler", (CRMRequestHandler,), {})
    store = CRMStore(project_dir)
    handler_class.store = store
    try:
        httpd = ThreadingHTTPServer((host, port), handler_class)
    except OSError as exc:
        store.logger.error("startup", "error", ERROR_CODES["startup"], "CRM 服务监听失败", {"error_type": type(exc).__name__}, {"host": host, "port": port})
        raise
    store.logger.info("startup", "success", ERROR_CODES["startup"], "CRM 服务已创建", {"host": host, "port": httpd.server_port}, {"operation": "server_create"})
    return httpd


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="启动本地客户 CRM 看板")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认仅本机")
    parser.add_argument("--port", default=8765, type=int, help="监听端口")
    args = parser.parse_args(argv)
    if not (1 <= args.port <= 65535):
        parser.error("端口必须在 1-65535 之间")
    server = create_server(args.host, args.port)
    server.RequestHandlerClass.store.logger.info("startup", "listening", ERROR_CODES["startup"], "CRM 服务开始监听", {"host": args.host, "port": server.server_port}, {"operation": "serve_forever"})
    print(f"客户 CRM 看板已启动：http://{args.host}:{args.port}/")
    print(f"数据目录：{CLIENTS_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止 CRM 看板…")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
