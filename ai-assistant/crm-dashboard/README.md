# 客户 CRM 看板

## Agent 接手前置阅读

本目录有强制 A2A 接手门禁。任何 Agent 必须先完整阅读 `A2A_HANDOFF.md`、`logs/a2a-task-updates.jsonl` 和 `A2A_HANDOFF_INDEX.json`，输出当前状态/完成项/未完成项或已知问题/最新错误码/下一步/回滚入口摘要，并追加 `a2a.handoff_read_confirmed` 日志后，才能编写代码或需求。目录级 `AGENTS.md` 会重复并强制这一规则；最新日志为 `blocked` 或 `failed` 时必须先定位和记录错误。

这是一个仅本机使用的客户管理页面，运行时不需要 npm 或额外的 pip 包。后端使用 Python 标准库 HTTP 服务，前端使用原生 HTML/CSS/JavaScript。

## 启动

在项目根目录执行（Windows）：

```powershell
& "C:\Users\weihu\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" "D:\ai文件\llmwiki-study\ai-assistant\crm-dashboard\server.py"
```

然后打开 <http://127.0.0.1:8765/>。也可以双击桌面上的 `启动客户CRM看板.bat`，它是纯 ASCII + CRLF 的安全入口，只调用同目录 ASCII 文件 `crm-dashboard-launcher.ps1`。PowerShell 启动器会检查项目和 Python、先探测健康接口；服务未运行时以隐藏后台进程启动，并轮询健康接口后打开浏览器；服务已运行时直接打开页面，不重复启动。服务默认只监听 `127.0.0.1`。

启动器的诊断输出写入 `logs/launcher.stdout.log`、`logs/launcher.stderr.log`，端口占用和健康轮询写入 `logs/launcher.jsonl`。启动失败时终端会输出错误码和具体原因；如需停止服务，可在任务管理器中确认命令行后停止对应 CRM Python 进程，或按交接文档的安全步骤操作。

如果当前电脑已将 Python 加入 PATH，也可以运行：

```powershell
python "D:\ai文件\llmwiki-study\ai-assistant\crm-dashboard\server.py"
```

可用参数：`--host 127.0.0.1 --port 8765`。

## 数据与 API

看板启动后每次读取并合并以下原始数据：

- `../clients/_index.md`
- `../leads/pipeline.md`
- `../clients/*.md`（以下划线开头的模板和索引不作为客户）

同一 `client_id` 的客户详情以档案为主；索引补齐缺失字段；pipeline 的 `status`、`next_action`、`updated` 作为当前跟进面最新值。新增或编辑会同步回上述 Markdown 文件，不会建立第二套数据库。更新档案时只修改目标字段和 `## Notes`，保留 Outreach Log 等无关段落。

页面按 `source` 自动分成两个板块：含 `alibaba` 或“阿里”的来源归入“阿里客户”，其余归入“邮件客户”。板块标签会显示数量，并独立作用于统计、搜索和筛选；邮件客户新建固定写入 `source=email_manual`，阿里客户新建固定写入 `source=alibaba`。阿里客户允许所有表单字段为空，空表单也会生成安全唯一 ID，并以“未命名阿里客户”作为显示名兜底；邮件客户仍要求公司名称。

新增客户表单提供本机草稿箱。表单发生实际改动后，通过右上角关闭、取消、遮罩或 Escape 退出都会先询问“继续编辑 / 不保存 / 保存到草稿箱”；草稿可浏览、恢复、更新和确认删除，恢复不会创建客户，正式创建成功后会移除对应草稿。草稿只写入当前浏览器的 `localStorage`，不进入 `clients`、索引、pipeline 或结构化运行日志（`CRM-DRAFT-001`）。

Alibaba 新增表单的产品区域已精简为 `product_raw` 产品原文、`product_codes` 内部编码和 `product_names` 产品名称三项；香型、用途、数量、规格、目标价格和其他要求不再出现在新增界面，可统一写入备注。旧字段仍由后端读取并保留，确保历史客户档案与 CSV 兼容。

批量产品拆分会返回 `product_items`（按原文顺序的 `{code, name}` 数组），并生成两列换行文本。除原有标签、`SL-001 | Rose` 和“编码在前”格式外，也支持 Alibaba 常见的“序号 + 产品名称 + 内部编码 + 价格 + 日期”表格行；Tab 或连续空格可分列，`FY01 4866E` 这类编码内部空格会保留，编码格中的全角/半角括号说明会被剥离并只保留主编码，括号内备用编码与价格不会成为额外产品。产品名中的年份/型号不会误作编码，`✅`、`⚠️` 状态不会混入两列。两区默认显示 10 行（可滚动编辑），一次支持识别 50 条产品，可分别复制到 Excel；缺失侧仍保留空位，总行数保持对齐（`CRM-BULK-COPY-001`）。

客户卡片支持客户端分页：数据处理顺序固定为当前板块 → 关键词/下拉筛选 → 排序 → 分页切片，默认每页 12 条，可切换 24/48 条。分页摘要同时显示当前范围、筛选后总数和当前板块总数；页码使用首尾页与当前页邻近页的紧凑省略号，首尾按钮会在边界禁用。搜索、筛选、排序、重置、板块切换和每页数量变化会回到第 1 页，刷新或结果变化会自动校正页码；无结果时隐藏分页导航，只有一页时保留摘要与每页选择。分页控件支持键盘焦点、ARIA 当前页标识和窄屏换行（`CRM-PAGINATION-001` 为分页动作/状态异常诊断码）。

浏览器复核记录：主审复现 P2 `CRM-PAGINATION-001`——阿里仅 1 条或搜索命中 1 条时，JavaScript 虽设置分页边界按钮 `hidden=true`，但 `.page-button { display: inline-grid; }` 覆盖浏览器默认隐藏样式，导致“上一页/下一页”仍可见。已补充 `.page-boundary[hidden] { display: none; }` 并加入静态回归断言。主审已通过邮件客户 76 条→7 页、上一页/下一页与末页、每页 24→4 页、48→2 页、筛选回第一页，以及批量产品 12 条、复制 12 行、空行精确保留、manual 保护和取消后总数 77；两个审核子 Agent 的浏览器会话分别因浏览器阻塞/额度失败记为 `CRM-A2A-002`，最终由主 Agent Browser 补验。上述复核未修改真实客户数据。

2026-08-29 Browser 复核：用户给出的 15 条产品精确拆为 15 行编码和 15 行名称，首尾、第 5/6/8/9 条、内部空格编码及排除备用编码均通过；两个复制按钮分别复制精确 15 行。草稿退出询问、保存、恢复、原草稿更新不重复、Escape/取消路径通过；390×844 无横向溢出，控制台 error/warning 为 0，客户总数保持 77。

2026-08-29 50 条容量复核：使用名称在前且名称含数字的 50 行样例，页面显示“识别 50 项产品”，编码与名称各 50 行，第 1/25/50 条对应正确；两列分别复制精确 50 行。主审同时修复了数字名称可能被误判为编码的歧义，未创建客户，健康检查仍为 77 位客户。

2026-08-29 带价格/日期表格复核：用户消息中可见的 18 条记录（最大序号为 27，但有 9 个序号未包含在粘贴文本中）原先只识别 15 条；修复编码括号说明后页面识别 18/18，原漏行全部恢复，编码/名称分别复制 18 行，备用编码不进入主编码列，console error/warning 为 0。

接口如下：

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/health` | 服务健康检查与客户数量 |
| GET | `/api/clients` | 合并后的客户、筛选枚举与统计 |
| GET | `/api/clients/{client_id}` | 读取一位客户 |
| POST | `/api/clients` | 创建客户档案并同步索引/pipeline |
| PATCH | `/api/clients/{client_id}` | 编辑资料、状态、下一步行动或备注 |
| POST | `/api/product-info/parse` | 输入 `raw_text`，返回产品拆分建议、批量编码/名称及 `product_items`（中英文标签与数量/价格/用途启发式） |
| GET | `/api/clients/export.csv?channel=alibaba` | 导出带 UTF-8 BOM 的 Alibaba CSV |

允许的 pipeline 状态为 `new`、`researched`、`outreach_1/2/3`、`replied`、`sampling`、`quoting`、`paid`、`won`、`lost`、`disqualified`、`cold`。分数限制为 0–100，等级为 A/B/C；所有写入采用 UTF-8。

Alibaba CSV 列顺序固定为：ID、姓名、公司、地址、电话、邮箱、产品原文、产品名称、内部编码、批量产品名称、香型要求、产品用途、产品数量、产品规格、目标价格、其他要求、备注。页面使用带 `href`/`download` 属性的直接下载链接，服务器同时返回 `Content-Disposition`；原文及两个批量换行字段中的逗号、换行由 CSV 编码处理，Excel 可直接打开中文。

## 结构化日志与错误码

服务运行后会自动创建 `logs/crm-dashboard.jsonl`。每行都是 UTF-8 JSON，包含 `timestamp`、`level`、`event`/`task_phase`、`status`、`error_code`、`message`、`details` 和 `context`。会记录服务启动、API 请求、数据加载、新建、更新、校验失败、文件写入失败及未捕获异常；日志上下文只保留诊断所需的字段名、计数和类型，邮箱、电话、备注、下一步行动正文及完整 Markdown 会脱敏或不写入。

稳定错误码清单：

| 错误码 | 含义 |
|---|---|
| `CRM-OK-001` | 成功或正常完成 |
| `CRM-STARTUP-001` | 服务创建/监听失败或启动阶段事件 |
| `CRM-REQUEST-001` | 请求接收阶段事件 |
| `CRM-VALIDATION-001` | 请求字段或业务状态校验失败 |
| `CRM-PARSE-001` | Markdown/UTF-8 解析失败 |
| `CRM-LOAD-001` | 客户源文件读取失败 |
| `CRM-WRITE-001` | 客户档案、索引或 pipeline 写入失败 |
| `CRM-NOTFOUND-001` | 指定客户或路径不存在 |
| `CRM-API-001` | API 路径或接口处理失败 |
| `CRM-PRODUCT-PARSE-001` | 产品原文拆分成功或输入校验失败（接口专用诊断码） |
| `CRM-BULK-PRODUCT-PARSE-001` | 批量产品编码/名称拆分成功；日志仅记录条数、命中字段和耗时 |
| `CRM-BULK-COPY-001` | 批量编码/名称复制列为空或复制失败；复制时保留 Excel 行占位 |
| `CRM-DRAFT-001` | 新增客户草稿的浏览器存储、恢复或退出保护异常 |
| `CRM-PAGINATION-001` | 客户端分页状态或动作异常；诊断只记录动作和页码，不记录客户内容 |
| `CRM-UI-001` | 前端交互修复/审核事件 |
| `CRM-UNEXPECTED-001` | 未捕获异常 |
| `CRM-LAUNCH-001` | 启动器配置或预检失败（项目/Python/日志准备） |
| `CRM-LAUNCH-002` | Python CRM 服务进程无法启动或启动后退出 |
| `CRM-LAUNCH-003` | 8765 端口或健康检查失败/超时 |
| `CRM-GIT-001` | GitHub 获取或推送连接失败；记录网络错误和安全重试状态，不执行强制推送 |

所有 API 错误响应都带 `error_code`，前端会把可读错误显示在 Toast 或错误状态中。日志文件属于运行数据，不应手动编辑；服务重启会继续追加。

## 测试

测试只在临时目录中创建 Markdown，不会修改真实客户数据：

```powershell
& "C:\Users\weihu\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest discover -s "D:\ai文件\llmwiki-study\ai-assistant\crm-dashboard\tests" -v
```

当前共 24 项测试，覆盖中文模板与旧版 `field/value` 表格解析、三源合并和板块归类、空 Alibaba 新建、地址与历史产品字段持久化、旧标签格式、12 条混合批量格式、历史 15 条目标样例、50 条容量样例、18 条价格/日期/编码括号说明样例、半角括号说明、编码内部空格、状态过滤、缺失侧重读、索引/pipeline/档案同步、产品解析与 BOM CSV API、敏感日志脱敏，以及健康检查和客户列表 API；前端静态回归检查草稿箱与统一退出门禁、精简产品区域、两列复制 fallback、manual 保护、CSV 和分页/移动端合同。

## 安全边界

这是本机工具，不包含登录、远程部署、自动发信或外部采集。服务不主动打开浏览器；桌面批处理文件仅负责启动本地服务并打开 `127.0.0.1` 页面。
