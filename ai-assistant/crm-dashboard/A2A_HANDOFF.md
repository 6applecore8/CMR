# CRM Dashboard · A2A 交接状态

更新时间：2026-08-28
状态：双板块与 Alibaba 产品拆分已实现；已修复 CRM-PRODUCT-PARSE-001 标签边界、二次原文刷新和 CSV 直接下载链路；最终针对性 Browser 复核因无可用浏览器阻塞，不标记 browser_qa passed

## 当前状态

本地 CRM 看板已实现于 `ai-assistant/crm-dashboard/`。服务使用 Python 标准库，默认监听 `127.0.0.1:8765`；前端使用原生 HTML/CSS/JavaScript，不需要 npm 或额外 pip 包。桌面启动文件为 `C:\Users\weihu\Desktop\启动客户CRM看板.bat`。

## 已完成

- 扫描并合并 `clients/_index.md`、`leads/pipeline.md` 与全部客户 Markdown；兼容中文模板和旧版 `field/value` 表格。
- 提供响应式中文卡片看板：统计、关键词搜索、状态/等级/市场/来源/排序筛选、详情弹窗、完整原始档案展开、加载/空态/错误态/Toast 与键盘操作。
- 新增客户：支持 Alibaba 来源、联系人、邮箱、电话、地区、产品兴趣、等级、分数、状态、下一步行动和备注；写入客户档案并同步索引/pipeline。
- 双板块：source 含 `alibaba`/“阿里”归入 Alibaba，其余归入邮件；标签显示数量并作用于统计、搜索、筛选和新增表单。Alibaba 新建所有字段可空，空表单使用“未命名阿里客户”显示名和安全唯一 ID；邮件新建固定 `source=email_manual`。
- 新增独立 `address` 字段，兼容旧 Markdown 解析、详情展示、编辑和持久化；Alibaba 产品原文保留在 `product_raw`，并可拆分到产品名称、香型要求、用途、数量、规格、目标价格和其他要求。
- 新增 `POST /api/product-info/parse`：中英文标签、换行/逗号/分号/连续 key:value 与数量/价格/常见用途启发式；前端 debounce 建议可编辑且不覆盖手改字段，`product_interest` 同步摘要。
- Alibaba CSV 导出采用 UTF-8 BOM 和固定列顺序，接口为 `/api/clients/export.csv?channel=alibaba`。
- 已根据 Browser QA 修复产品解析 P2：支持 `Target` 标签、无冒号连续标签及换行/逗号/分号/竖线/斜杠边界；二次原文解析会刷新未标记 manual 字段并保留手改字段。CSV 改为带 `href`/`download` 的直接链接，保留服务器 Content-Disposition，避免 Blob 下载事件不可见。
- 编辑客户资料、状态、下一步行动和备注；保留无关的 Outreach Log 等沟通段落并同步更新时间。
- 服务健康检查与输入校验；客户 ID 防路径穿越，邮箱/分数/等级/状态有合理限制。
- 结构化日志：运行时自动创建 `logs/crm-dashboard.jsonl`，记录启动、API 请求、数据加载、新建、更新、校验失败、写入失败和未捕获异常；`details`/`context` 递归脱敏，不记录邮箱、电话、备注、下一步正文和完整 Markdown。

## 变更文件

- `server.py`：解析/合并、持久化、同步、日志、HTTP API。
- `index.html`：中文看板、详情与新增/编辑表单。
- `styles.css`：米白/深墨绿/琥珀视觉系统和响应式布局。
- `app.js`：筛选、卡片、弹窗、校验、API 交互和 Toast。
- `tests/test_server.py`：解析、合并/板块归类、空 Alibaba、新字段持久化、产品解析、CSV/API、旧邮件回归、HTTP、日志脱敏和错误码测试。
- `README.md`：启动、数据策略、API、日志与错误码说明。
- `logs/.gitkeep`：保留运行日志目录；实际 JSONL 日志由服务按需创建。
- `logs/a2a-task-updates.jsonl`：追加本次 UI 修复、测试与交接状态事件。
- `logs/launcher.jsonl`、`logs/launcher.stdout.log`、`logs/launcher.stderr.log`：桌面启动器的端口/健康诊断与后台服务输出（运行时生成）。
- `A2A_HANDOFF.md`：本交接记录。
- `C:\Users\weihu\Desktop\启动客户CRM看板.bat`：绝对项目路径启动服务并打开本机页面。
- `C:\Users\weihu\Desktop\crm-dashboard-launcher.ps1`：同目录 ASCII 名 PowerShell 启动器，负责预检、隐藏后台启动、健康轮询和重复调用短路。

## 测试与联调状态

- 2026-08-28 独立真实 Browser QA：首屏阿里 1、邮件 76、合计 77；板块切换、阿里/邮件卡片、阿里表单全字段非必填与 `source=alibaba`、邮件公司必填与 `source=email_manual`、两类取消不提交、当前板块搜索均通过；未写入真实客户数据。
- 2026-08-28 产品原文 debounce 复核发现 P2（`CRM-PRODUCT-PARSE-001`）：六项英文标签可填入六栏，但产品规格值混入 Target 标签；二次原文更新时未手改的规格栏不更新；手动修改产品名称可保持。原文完整样例未写入日志，详见 `logs/a2a-task-updates.jsonl`。
- 2026-08-28 Alibaba CSV 导出按钮点击后 Browser download 事件三次超时，未取得文件名；390×844 检查期间浏览器连接中断，按技能一次恢复仍返回 `No browser is available`（`CRM-A2A-002`）。控制台 error/warning 读取为空；page-error 未完成专项读取。
- 本轮代码回归已覆盖上述 P2：`Target`/连续无冒号解析、二次原文更新中自动字段刷新与手改字段保护、直接 CSV 链接静态结构；等待可用浏览器复核下载文件名和最终视觉行为。
- 2026-08-28 最终极简 Browser 复核按技能重新初始化并只恢复一次；`getForUrl(http://127.0.0.1:8765/)` 返回 `No browser is available`，`browsers.list()` 为 `[]`。因此本轮未能验证修复版 slash/no-colon 六栏、规格边界、二次刷新/手改保护、取消后 77、CSV 下载文件名、390×844 或 console；未提交表单，真实客户数据未改变。详见 `logs/a2a-task-updates.jsonl` 中 `browser_qa.final_retest_unavailable`（`CRM-A2A-002`）。

- 已完成 Python `py_compile`。
- 已完成 Node `--check app.js`。
- 已完成 `python -m unittest discover -s ai-assistant/crm-dashboard/tests -v`：11 项通过。
- 已完成产品解析、双板块、空 Alibaba、地址和拆分字段持久化、UTF-8 BOM CSV API 以及产品日志不落原文的临时目录回归测试；未写入真实客户数据，未停止现有 8765 服务。
- 已增加前端静态回归断言：确认 `#add-cancel` 存在并绑定 `closeModal(#add-dialog)`。
- 已用真实数据做过只读扫描检查：合并 77 位客户，健康接口和客户列表接口返回正常。
- 2026-08-28 已用真实 Codex In-app Browser 完成首屏、77 位客户、关键词搜索、状态筛选、详情/原始档案、Escape、编辑字段回填、新增 Alibaba 来源、空白必填校验与 390×844 窄屏 DOM/截图联调；未提交新增或编辑数据。
- 浏览器会话中断后重连失败（`Browser is not available: -c09f-4b17-a107-a834eda1f369`；重新初始化后 `No browser is available`，`browsers.list()` 为 `[]`），因此最终控制台/page-error 读取未完成。
- 针对 CRM-UI-001 修复的最后一次独立复核未能启动：`getForUrl(http://127.0.0.1:8765/)` 返回 `No browser is available`，按故障说明检查 `browsers.list()` 仍为 `[]`；因此不能将 `CRM-UI-001` 标记为 resolved，也不能将 `browser_qa` 标记为 passed。
- 2026-08-28 已用真实 `cmd.exe /d /c call` 执行桌面 BAT：首次启动输出 `CRM-LAUNCH-003: CRM is ready at http://127.0.0.1:8765/ (77 clients)`，第二次输出 `CRM-LAUNCH-003: CRM is already running; opened http://127.0.0.1:8765/ (77 clients)`；两次 PID 相同（15100），未重复启动。测试结束后仅停止该 PID，8765 已无监听。
- 2026-08-28 10:10:57 的最终幂等验收再次用真实 `cmd.exe /d /c call C:\Users\weihu\Desktop\启动客户CRM看板.bat` 执行：退出码 0，输出 `CRM-LAUNCH-003 ... already running (77 clients)`；调用前后监听 PID 均为 27752，未启动新进程。`/api/health` 返回 `status=ok`、`service=crm-dashboard`、`clients=77`。
- 启动器文件验收：桌面 BAT 存在且调用同目录 `crm-dashboard-launcher.ps1`；185 字节、无 BOM、0 个非 ASCII 字节、5 行 CRLF、0 个孤立 LF、以 CRLF 结尾。`launcher.jsonl` 最新记录结构字段齐全，状态为 `already_running` / `CRM-LAUNCH-003`；`launcher.stderr.log` 长度为 0。
- 页面可见性验收按 Browser skill 尝试一次，但当前无可用浏览器（`No browser is available`，`browsers.list()` 为 `[]`），故未以浏览器确认标题/客户卡片；未使用替代浏览器工具，未改客户数据。
- 双板块/产品拆分专项复核按 Browser skill 尝试一次：`getForUrl(http://127.0.0.1:8765/)` 返回 `No browser is available`，恢复说明要求的 `browsers.list()` 为 `[]`；首屏板块、1/76/77、表单 required/source、产品 debounce 拆分/手动保护、取消、CSV 下载、板块搜索、390×844 和 console/page errors 均未执行，未使用替代工具。

## 稳定错误码

`CRM-OK-001`、`CRM-STARTUP-001`、`CRM-REQUEST-001`、`CRM-VALIDATION-001`、`CRM-PARSE-001`、`CRM-LOAD-001`、`CRM-WRITE-001`、`CRM-NOTFOUND-001`、`CRM-API-001`、`CRM-PRODUCT-PARSE-001`、`CRM-UI-001`、`CRM-LAUNCH-001`、`CRM-LAUNCH-002`、`CRM-LAUNCH-003`、`CRM-UNEXPECTED-001`。含义及 API 行为详见 `README.md`。

## 已知问题 / 审核注意

- **P2 历史问题（CRM-UI-001，代码已修复、浏览器待确认）：** 原审计曾复现新增客户弹窗底部“取消”（`#add-cancel`）点击无效，而右上角关闭可用；现已补充 `#add-cancel` → `closeModal(#add-dialog)` 事件绑定，预期关闭且不提交。最后一次针对性复核因浏览器不可用未执行，不能视为已验证。
- 详情原始档案只在展开后展示；索引/pipeline-only 客户在首次编辑时才会补建详情 Markdown。
- pipeline 的已有客户按原表位置更新；若手动改变等级，记录字段会同步，但不会自动重排到另一分级表。
- 日志是追加式 JSONL，若目录无写权限，日志器只向 stderr 报告，不应阻断 CRM 主流程。
- 桌面批处理中的 Python 路径优先使用当前 Codex 运行时，找不到时回退到 PATH 中的 `python`。
- 本轮双板块专项浏览器联调被 Browser 不可用阻塞；双板块标签、表单切换、产品 debounce 和下载行为仍需在可用浏览器中针对性确认。当前产品解析/下载代码已修复，状态仍保持“待针对性浏览器复核”。
- **CRM-LAUNCH-001 历史问题已修复：** 原 BAT 为 UTF-8 无 BOM + LF，且直接使用 `start ... /b`，在真实 `cmd.exe` 中触发路径/`/b` 解析错误；现改为 ASCII + CRLF BAT，仅调用同目录 PowerShell 启动器。首次重试还发现并修复 Windows PowerShell 5.1 不支持 `New-Item -LiteralPath` 的兼容性问题。

## 回滚指引（仅记录步骤，不在此执行）

1. 停止正在运行的本地 CRM 服务。
2. 备份当前 `ai-assistant/crm-dashboard/`、`ai-assistant/clients/`、`ai-assistant/leads/pipeline.md` 与 `logs/`。
3. 根据项目版本控制或用户指定的安全副本，恢复本次新增的 CRM 看板代码文件；不要直接删除或移动客户主数据。
4. 如需撤销某次客户新建/编辑，先由用户确认目标 `client_id`，再人工恢复对应 Markdown、索引行和 pipeline 行。
5. 重新运行 README 中的测试和健康检查，确认恢复后的三源数据可读。
