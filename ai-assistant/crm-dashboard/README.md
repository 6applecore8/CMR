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

阿里表单增加独立 `address` 地址字段和 `product_raw` 产品原文。粘贴原文后，前端会调用拆分接口建议填写 `product_name`、`fragrance_requirement`、`product_application`、`product_quantity`、`product_specification`、`target_price`、`other_requirements`；解析支持换行、逗号、分号、竖线、斜杠分隔，以及 `Product perfume oil` 这类无冒号连续标签。每次新原文都会刷新未标记为手改的拆分字段，手动改过的字段不会被后续 debounce 结果覆盖，原文始终保留。`product_interest` 会由产品名/用途/香型生成短摘要，以兼容既有搜索和卡片。

批量产品拆分会额外返回 `product_items`（按原文顺序的 `{code, name}` 数组），并生成 `product_codes`、`product_names` 两个换行字段；支持“内部编码 / 产品编码 / Code / SKU / Item No.”和“产品名称 / 品名 / Product name / Name”等标签，也支持 `SL-001 | Rose Fragrance Oil`、Tab、逗号、冒号和“编码在行首 + 名称”格式。无标签编码要求同时含字母和数字，避免把 `25kg` 等数量当成编码；明确编码标签允许纯数字。两列在新增表单中可编辑、显示识别数量并分别复制到 Excel 单列，空缺侧保留对应行。复制只会逐行 trim 并统一换行，保留首部、中间、尾部空行及总行数；有空位时成功提示会标注“含空位”，整列为空才提示无内容（`CRM-BULK-COPY-001`）。

客户卡片支持客户端分页：数据处理顺序固定为当前板块 → 关键词/下拉筛选 → 排序 → 分页切片，默认每页 12 条，可切换 24/48 条。分页摘要同时显示当前范围、筛选后总数和当前板块总数；页码使用首尾页与当前页邻近页的紧凑省略号，首尾按钮会在边界禁用。搜索、筛选、排序、重置、板块切换和每页数量变化会回到第 1 页，刷新或结果变化会自动校正页码；无结果时隐藏分页导航，只有一页时保留摘要与每页选择。分页控件支持键盘焦点、ARIA 当前页标识和窄屏换行（`CRM-PAGINATION-001` 为分页动作/状态异常诊断码）。

浏览器复核记录：主审复现 P2 `CRM-PAGINATION-001`——阿里仅 1 条或搜索命中 1 条时，JavaScript 虽设置分页边界按钮 `hidden=true`，但 `.page-button { display: inline-grid; }` 覆盖浏览器默认隐藏样式，导致“上一页/下一页”仍可见。已补充 `.page-boundary[hidden] { display: none; }` 并加入静态回归断言。主审已通过邮件客户 76 条→7 页、上一页/下一页与末页、每页 24→4 页、48→2 页、筛选回第一页，以及批量产品 12 条、复制 12 行、空行精确保留、manual 保护和取消后总数 77；两个审核子 Agent 的浏览器会话分别因浏览器阻塞/额度失败记为 `CRM-A2A-002`，最终由主 Agent Browser 补验。上述复核未修改真实客户数据。

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

当前共 18 项测试，覆盖中文模板与旧版 `field/value` 表格解析、三源合并和板块归类、空 Alibaba 新建、地址与产品拆分字段持久化、中文/英文标签和数量/价格/用途启发式、12 条混合批量产品的顺序/对应/去重/数量安全、连续标签和纯数字编码、缺失侧重读、索引/pipeline/档案同步、编辑时保留沟通记录、产品解析与 BOM CSV API、批量字段重读与 CSV 列、敏感日志脱敏，以及健康检查和客户列表 API；前端静态回归检查板块、拆分接口、复制 fallback（含空位保留）、manual 保护、CSV、新增弹窗取消按钮和分页合同（默认/可选页大小、筛选排序顺序、重置/校正、ARIA 与移动端样式）。

## 安全边界

这是本机工具，不包含登录、远程部署、自动发信或外部采集。服务不主动打开浏览器；桌面批处理文件仅负责启动本地服务并打开 `127.0.0.1` 页面。
