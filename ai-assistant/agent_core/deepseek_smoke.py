"""显式在线冒烟：只规划固定合成问题，不读客户文件；会产生一次 API 费用。"""

import json
import logging

from .contracts import DomainError
from .deepseek import create_model_planner


def main() -> int:
    """使用当前进程密钥测试工具规划；不输出密钥、异常原文或提供方响应体。"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        planner = create_model_planner()
        call = planner.plan("Count all tier A customers.")
        print(json.dumps({"provider": "deepseek", "model": planner.config.model,
                          "tool": call.name, "arguments": call.arguments}, ensure_ascii=True))
        return 0
    except DomainError as exc:
        print(json.dumps({"code": exc.code, "message": exc.message}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
