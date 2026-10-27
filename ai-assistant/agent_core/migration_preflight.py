"""只读检查旧版 CRM 数据可用性，不导入、不修改、不记录客户正文。"""

import argparse
import json
import os
from pathlib import Path

MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_PROFILE_FILES = 10000
MAX_TOTAL_BYTES = 64 * 1024 * 1024


def _check_file(path: Path) -> str:
    """区分缺失、损坏和不可读；任何一种都不能当作正常空数据。"""
    try:
        if path.is_symlink():
            return "link_rejected"
        if not path.exists():
            return "missing"
        if not path.is_file():
            return "not_file"
        with path.open("rb") as stream:
            content = stream.read(MAX_FILE_BYTES + 1)
        if len(content) > MAX_FILE_BYTES:
            return "too_large"
        content.decode("utf-8-sig")
        return "readable"
    except UnicodeDecodeError:
        return "invalid_utf8"
    except OSError:
        return "unreadable"


def inspect_source(root: Path) -> dict:
    """返回不含姓名、地址、原始路径或正文的只读汇总；不推断负责人。"""
    root = Path(root)
    try:
        if root.is_symlink():
            return {"state": "UNAVAILABLE", "reason": "root_link_rejected", "profiles": None,
                    "ownership": "UNRESOLVED", "migrationAllowed": False}
        if not root.is_dir():
            return {"state": "UNAVAILABLE", "reason": "root_missing_or_unreadable", "profiles": None,
                    "ownership": "UNRESOLVED", "migrationAllowed": False}
        clients = root / "clients"
        leads = root / "leads"
        if clients.is_symlink() or leads.is_symlink():
            return {"state": "UNAVAILABLE", "reason": "directory_link_rejected", "profiles": None,
                    "ownership": "UNRESOLVED", "migrationAllowed": False}
        if not clients.is_dir() or not leads.is_dir():
            return {"state": "UNAVAILABLE", "reason": "source_directory_missing", "profiles": None,
                    "ownership": "UNRESOLVED", "migrationAllowed": False}
        index_status = _check_file(clients / "_index.md")
        pipeline_status = _check_file(leads / "pipeline.md")
        issues = {}
        count = 0
        total_bytes = 0
        with os.scandir(clients) as entries:
            for entry in entries:
                if entry.name.startswith("_") or not entry.name.lower().endswith(".md"):
                    continue
                count += 1
                if count > MAX_PROFILE_FILES:
                    return {"state": "UNAVAILABLE", "reason": "profile_limit_exceeded", "profiles": None,
                            "ownership": "UNRESOLVED", "migrationAllowed": False}
                size = entry.stat(follow_symlinks=False).st_size
                total_bytes += size
                if total_bytes > MAX_TOTAL_BYTES:
                    return {"state": "UNAVAILABLE", "reason": "source_size_limit_exceeded", "profiles": None,
                            "ownership": "UNRESOLVED", "migrationAllowed": False}
                status = _check_file(Path(entry.path))
                if status != "readable":
                    issues[status] = issues.get(status, 0) + 1
        source_ok = index_status == "readable" and pipeline_status == "readable" and not issues
        return {"state": "READABLE_REQUIRES_REVIEW" if source_ok else "UNAVAILABLE",
                "index": index_status, "pipeline": pipeline_status,
                "profiles": {"total": count, "issues": issues},
                "ownership": "UNRESOLVED", "migrationAllowed": False,
                "note": "Readability is not a backup, parse validation, ownership mapping, or migration approval."}
    except OSError:
        return {"state": "UNAVAILABLE", "reason": "source_unreadable", "profiles": None,
                "ownership": "UNRESOLVED", "migrationAllowed": False}


def main() -> int:
    parser = argparse.ArgumentParser(description="只读检查 CRM 历史资料，不修改或迁移文件")
    parser.add_argument("--root", required=True, type=Path, help="包含 clients/ 和 leads/ 的 ai-assistant 目录")
    args = parser.parse_args()
    report = inspect_source(args.root)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["state"] == "READABLE_REQUIRES_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())