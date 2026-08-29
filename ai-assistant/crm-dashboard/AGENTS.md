# CRM Dashboard Agent 接手门禁

本目录继承仓库根目录 `AGENTS.md`。任何 Agent 开始工作前，必须执行以下顺序：

1. 完整阅读 `A2A_HANDOFF.md`。
2. 完整阅读 `logs/a2a-task-updates.jsonl`，以了解任务演进、错误码、阻塞和最新状态。
3. 阅读 `A2A_HANDOFF_INDEX.json`，核对阅读顺序、最新事件和回滚入口。
4. 在开始代码或需求编写前，先输出接手摘要：当前状态、已完成项、未完成项/已知问题、最新错误码、下一步和回滚方式。
5. 将接手确认追加到 `logs/a2a-task-updates.jsonl`，事件名为 `a2a.handoff_read_confirmed`；不得写入客户原文、邮箱、电话、地址、备注或完整 Markdown。

若最新日志状态为 `blocked` 或 `failed`，先定位并记录错误，不得绕过门禁直接修改代码。未完成上述阅读和摘要，不得编写代码、改变需求或操作客户数据。

索引标记文件：`A2A_HANDOFF_INDEX.json`。
