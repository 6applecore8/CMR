# CRM Dashboard · A2A 交接状态

更新时间：2026-09-30
状态：邮件客户新增/编辑支持粘贴整段联系信息自动识别姓名、电话、地址；这三个字段在表单、详情和卡片前置分组；每日清单、Git 数据隔离、姓名优先展示、客户完整编辑、自定义标签、长产品详情折叠/完整列复制、草稿箱和 Alibaba 50 条产品拆分均已实现；可按交接门禁接手

## 接手门禁（A2A_HANDOFF_INDEX）

任何 Agent 接手本目录任务时，必须先完整阅读以下文件，再开始编写代码、修改需求或运行会改变客户数据的操作：

1. `A2A_HANDOFF.md`（本文件，先了解目标、完成项、风险与回滚步骤）。
2. `logs/a2a-task-updates.jsonl`（逐行了解任务过程、错误码、阻塞记录和最新状态）。
3. `A2A_HANDOFF_INDEX.json`（机器可读的阅读顺序、接手条件和最新日志索引）。

阅读后必须先形成接手摘要：当前状态、已完成项、未完成项/已知问题、最新错误码、下一步和回滚入口。只有确认最新日志事件为 `status=passed` 或明确的 `in_progress` 且任务目标已理解，才能进行代码或需求编写；若最新事件为 `blocked`/`failed`，应先定位错误并追加日志，不得绕过门禁直接改代码。接手确认应追加一条不含客户原文、联系方式或备注的 JSONL 记录，事件名使用 `a2a.handoff_read_confirmed`。

该门禁由目录级 `AGENTS.md` 强制执行；`A2A_HANDOFF_INDEX.json` 是索引标记，不替代本文件和完整日志阅读。

## 当前状态

本地 CRM 看板已实现于 `ai-assistant/crm-dashboard/`。服务使用 Python 标准库，默认监听 `127.0.0.1:8765`；前端使用原生 HTML/CSS/JavaScript，不需要 npm 或额外 pip 包。桌面启动文件为 `C:\Users\weihu\Desktop\启动客户CRM看板.bat`。

## 已完成

- 2026-09-30 联系信息粘贴识别：新增/编辑表单顶部可粘贴整段姓名、电话、地址文字，经 `POST /api/contact-info/parse` 拆分后填入对应字段；已手工修改的字段保留。姓名、电话、地址在表单、详情和卡片中前置分组。阿里客户同样可用；询盘混贴只把编号产品行同步到产品原文再拆两列，联系标签不会进入产品拆分。独立“产品原文”框仍按原文 debounce 拆分。错误码 `CRM-CONTACT-PARSE-001`。日志只记录长度、命中字段名和产品行数。回滚此项还原表单布局、解析函数、API 与前端粘贴控件。
- 2026-09-08 界面顺序：新增与编辑表单以联系人姓名为第一行、优先聚焦；阿里客户/邮件客户切换移入页面顶部草稿箱旁。保留原按钮 ID、计数与切换逻辑。回滚此项只需还原对应 HTML/CSS 布局及新增聚焦语句。
- 扫描并合并 `clients/_index.md`、`leads/pipeline.md` 与全部客户 Markdown；兼容中文模板和旧版 `field/value` 表格。
- 提供响应式中文卡片看板：统计、关键词搜索、状态/等级/市场/来源/排序筛选、详情弹窗、完整原始档案展开、加载/空态/错误态/Toast 与键盘操作。
- 新增客户：支持 Alibaba 来源、联系人、邮箱、电话、地区、产品兴趣、等级、分数、状态、下一步行动和备注；写入客户档案并同步索引/pipeline。
- 双板块：source 含 `alibaba`/“阿里”归入 Alibaba，其余归入邮件；标签显示数量并作用于统计、搜索、筛选和新增表单。Alibaba 新建所有字段可空，空表单使用“未命名阿里客户”显示名和安全唯一 ID；邮件新建固定 `source=email_manual`。
- 新增独立 `address` 字段；Alibaba 新增界面只保留产品原文、内部编码、产品名称和通用备注，香型/用途/数量/规格/目标价格/其他要求从新增界面移除，后端仍兼容历史字段与 CSV。
- 批量产品隔离：新增可持久化的 `product_codes`、`product_names` 与派生 `product_items`；支持中英文编码/名称标签、逗号/分号/竖线/斜杠/Tab/逐行格式、纯数字显式编码、数量安全过滤、顺序/空缺侧保留和完全重复项目去重；旧 `product_name` 只取第一项名称摘要。
- 名称在前的 Alibaba 表格行支持序号、Tab/连续空格、编码内部空格以及状态/括号备注过滤；用户 15 条目标样例精确输出为两列各 15 行，第 7/12 条同编码不同名称均保留。
- 批量识别容量已升级并实测至 50 条：页面明确显示 50 条能力，两列可滚动编辑；带序号的名称在前表格会优先选择后侧编码列，避免产品名中的年份/型号被误判为编码。
- 真实 Alibaba 表格的编码格可带全角/半角括号说明：解析只保留括号前主编码，忽略括号内备用编码/价格；后续价格和日期列不参与编码/名称结果。
- 对“序号 + 内部编码 + 产品名称 + 性别/浓度 + 香调 + 说明”等明确多列表格，只提取编码和相邻名称单元格；后续性别、浓度、香调、价格、日期和卖点说明全部忽略。名称在前/编码在后的旧格式继续取编码左侧名称，列识别仅使用 Tab 或连续两个以上空格，避免拆散名称内部普通空格。
- 新增本机草稿箱：所有新增表单退出路径统一询问，支持保存、浏览、恢复、更新和确认删除；草稿使用当前浏览器 `localStorage`，不写客户 Markdown/索引/pipeline，正式创建成功后清理对应草稿。
- 新增批量产品前端两列编辑区、识别数量/行对应提示和 `#copy-product-codes` / `#copy-product-names` 复制按钮（Clipboard API + 安全 fallback）；两列均纳入 manual 保护，重开新增弹窗会重置保护状态。复制仅逐行 trim/归一化换行，完整保留首部、中间、尾部空位及总行数。
- 已修复 P1 批量复制对齐问题（`CRM-BULK-COPY-001`）：不再过滤空行；只有整列为空才提示无内容，成功提示报告含空位在内的总行数；新增静态回归断言防止 `.filter(Boolean)` 回归。
- 客户卡片分页：处理顺序固定为当前板块 → 搜索/筛选 → 排序 → 分页切片；默认每页 12 条，可选 24/48 条；摘要显示当前范围、筛选总数和板块总数；页码提供首尾页/邻近页及省略号，边界按钮禁用；搜索、筛选、排序、重置、板块切换和刷新会重置或校正页码，移动端分页自动换行。
- 新增稳定诊断码 `CRM-PAGINATION-001`；正常分页不写敏感日志，若后续接入动作异常记录只允许包含动作和页码。
- 新增 `POST /api/product-info/parse`：中英文标签、换行/逗号/分号/连续 key:value 与数量/价格/常见用途启发式；前端 debounce 建议可编辑且不覆盖手改字段，`product_interest` 同步摘要。
- Alibaba CSV 导出采用 UTF-8 BOM 和固定列顺序，含独立“内部编码”“批量产品名称”列，接口为 `/api/clients/export.csv?channel=alibaba`。
- 已根据 Browser QA 修复产品解析 P2：支持 `Target` 标签、无冒号连续标签及换行/逗号/分号/竖线/斜杠边界；二次原文解析会刷新未标记 manual 字段并保留手改字段。CSV 改为带 `href`/`download` 的直接链接，保留服务器 Content-Disposition，避免 Blob 下载事件不可见。
- 编辑客户现覆盖公司、联系人姓名、职位、地区、地址、市场、渠道类型、邮箱、电话、等级/分数、状态、下一步行动和备注；产品摘要、原文、内部编码和产品名称可联合修改并写回档案。只有点击“根据原文重新拆分”才刷新两列，避免静默覆盖手工编码/名称；Alibaba 客户允许公司为空。
- 客户卡片 h3 和详情 dialog 标题统一采用联系人姓名优先；公司降为卡片副标题，并在详情“基本资料”中明确展示。联系人为空时回退有效公司，两者均空时使用原有渠道安全兜底；前后端 `display_name` 规则一致。
- 新增/编辑客户均支持自由创建自定义标签：逗号/中文逗号/分号/换行分隔，保序去重，最多 20 个且单个最多 30 字符；持久化为 `custom_tags`，卡片显示前三个及剩余数量，详情显示完整 chips，关键词搜索覆盖标签；标签正文纳入日志脱敏。
- Alibaba 详情的内部编码、批量产品名称和产品原文超过 15 条时默认仅显示前 15 条，可分别展开剩余条目并收起；关闭重开恢复默认收起。详情保留两列一键复制，始终复制完整原字段，不受折叠状态影响并保留空位对齐。
- 服务健康检查与输入校验；客户 ID 防路径穿越，邮箱/分数/等级/状态有合理限制。
- 结构化日志：运行时自动创建 `logs/crm-dashboard.jsonl`，记录启动、API 请求、数据加载、新建、更新、校验失败、写入失败和未捕获异常；`details`/`context` 递归脱敏，不记录邮箱、电话、备注、下一步正文和完整 Markdown。
- Git 数据隔离：仓库根 `.gitignore` 排除客户档案、线索、原始导入、业务产出、导出、备份和本地数据目录；新增自动化同时检查规则存在及 Git 索引零跟踪。现有本地客户文件不删除、不移动，看板继续从原路径读取；新克隆不会获得其他电脑的客户资料。
- 每日清单：看板新增独立“每日清单”区，任务按日期保存到当前浏览器 `localStorage`（键 `scentedland-crm:daily-checklist:v1`），支持日期前后切换、回到今天、新增、完成切换、编辑/Enter 保存、Escape 取消、删除确认和完成进度；不调用 `/api/`、不写客户 Markdown/索引/pipeline/结构化日志，不进入 Git 或 GitHub。

## 变更文件

- `server.py`：解析/合并、持久化、同步、日志、HTTP API。
- `index.html`：中文看板、详情与新增/编辑表单。
- `styles.css`：米白/深墨绿/琥珀视觉系统和响应式布局。
- `app.js`：筛选、卡片、弹窗、校验、API 交互和 Toast。
- `tests/test_server.py`：44 项测试，新增联系信息粘贴拆分、API 日志脱敏、姓名/电话/地址前置与粘贴控件静态回归；保留 Git 本地数据忽略规则和索引零跟踪检查、每日清单本地存储/日期/增删改查静态回归、多列表格相邻列提取、数字产品名/后续字母数字列冲突、Tab 空名称列、姓名优先、自定义标签、详情折叠/复制、客户编辑、草稿箱与分页回归。
- 仓库根 `.gitignore`：隔离 `clients`、`leads`、`output`、`raw`、跨系统 `outputs` 及 CRM 本地 data/exports/backups。
- `README.md`：启动、数据策略、API、日志与错误码说明。
- `logs/.gitkeep`：保留运行日志目录；实际 JSONL 日志由服务按需创建。
- `logs/a2a-task-updates.jsonl`：追加本次 UI 修复、测试与交接状态事件。
- `logs/launcher.jsonl`、`logs/launcher.stdout.log`、`logs/launcher.stderr.log`：桌面启动器的端口/健康诊断与后台服务输出（运行时生成）。
- `A2A_HANDOFF.md`：本交接记录。
- `C:\Users\weihu\Desktop\启动客户CRM看板.bat`：绝对项目路径启动服务并打开本机页面。
- `C:\Users\weihu\Desktop\crm-dashboard-launcher.ps1`：同目录 ASCII 名 PowerShell 启动器，负责预检、隐藏后台启动、健康轮询和重复调用短路。

## 测试与联调状态

- 2026-09-30 联系信息粘贴识别自动化复核：44/44 Python 测试通过，`py_compile`、`node --check app.js` 通过；覆盖中英文标签、无标签收货块、邮件签名、日期不误判为电话、API 不写原文，以及新增/编辑表单字段顺序与粘贴控件静态合同。未写入真实客户数据。本环境无浏览器 MCP，页面交互待用户刷新后验收。
- 2026-09-30 阿里产品拆分污染修复：联系粘贴不再把整段原文写入产品框；仅抽出编号产品行作为 `product_excerpt`。`Name:` 联系标签不再进入内部编码/产品名称两列。独立产品原文拆分保持原合同。
- 2026-09-04 每日清单自动化复核：41/41 Python 测试通过，`node --check app.js`、`git diff --check` 通过；静态合同确认任务只使用浏览器 `localStorage`，日期切换、进度、完成、编辑和删除事件均已绑定，未新增 API 或客户数据写入。
- 2026-09-04 每日清单独立审核：审核子 Agent 复核代码、文档、日志和 JSONL 均无阻断性问题，客户文件前后未变化；其独立浏览器实例受环境策略阻塞，记录为 `CRM-A2A-002`，不覆盖主 Agent 已确认的本地页面可见性，也不判定为产品缺陷。

- 2026-08-28 独立真实 Browser QA：首屏阿里 1、邮件 76、合计 77；板块切换、阿里/邮件卡片、阿里表单全字段非必填与 `source=alibaba`、邮件公司必填与 `source=email_manual`、两类取消不提交、当前板块搜索均通过；未写入真实客户数据。
- 2026-08-28 产品原文 debounce 复核发现 P2（`CRM-PRODUCT-PARSE-001`）：六项英文标签可填入六栏，但产品规格值混入 Target 标签；二次原文更新时未手改的规格栏不更新；手动修改产品名称可保持。原文完整样例未写入日志，详见 `logs/a2a-task-updates.jsonl`；代码修复历史仍保留。
- 2026-08-28 Alibaba CSV 导出按钮点击后 Browser download 事件三次超时，未取得文件名；390×844 检查期间浏览器连接中断，按技能一次恢复仍返回 `No browser is available`（`CRM-A2A-002`）。控制台 error/warning 读取为空；page-error 未完成专项读取。
- 本轮代码回归已覆盖上述 P2：`Target`/连续无冒号解析、二次原文更新中自动字段刷新与手改字段保护、直接 CSV 链接静态结构；批量编码/名称顺序、缺失侧、数量误判、Markdown 重读与 CSV 独立列也已覆盖；等待可用浏览器复核下载文件名、复制行为和最终视觉行为。
- 2026-08-28 最终极简 Browser 复核按技能重新初始化并只恢复一次；`getForUrl(http://127.0.0.1:8765/)` 返回 `No browser is available`，`browsers.list()` 为 `[]`。因此本轮未能验证修复版 slash/no-colon 六栏、规格边界、二次刷新/手改保护、取消后 77、CSV 下载文件名、390×844 或 console；未提交表单，真实客户数据未改变。详见 `logs/a2a-task-updates.jsonl` 中 `browser_qa.final_retest_unavailable`（`CRM-A2A-002`）。

- 已完成 Python `py_compile`。
- 已完成 Node `--check app.js`。
- 已完成 `python -m unittest discover -s ai-assistant/crm-dashboard/tests -v`：18 项通过（保留原 17 项并新增分页合同测试；未修改真实客户数据）。
- 已完成产品解析、双板块、空 Alibaba、地址和拆分字段持久化、UTF-8 BOM CSV API 以及产品日志不落原文的临时目录回归测试；未写入真实客户数据，未停止现有 8765 服务。
- 已增加前端静态回归断言：确认 `#add-cancel` 存在并绑定 `closeModal(#add-dialog)`，批量两列/复制按钮/Clipboard fallback/manual 保护存在且具备移动端样式。
- 2026-08-28 14:58 主 Agent 使用真实 Codex In-app Browser 完成最终补验：邮件 76 条默认 12 张/页共 7 页，next/末页/12、24、48 页大小/筛选和渠道重置均通过；单页边界按钮 P2 修复后确认隐藏。
- 同次 Browser 验收确认 12 条 synthetic 产品按顺序拆为 12 个编码和 12 个名称，两个复制按钮写入精确 12 行，`A1\n\nA3\n` 的中间及尾部空位完整保留；手改编码不被二次解析覆盖，未手改名称正常刷新；取消后仍为 77 位客户。
- 390×844 请求视口下文档有效宽度与滚动宽度均为 375，无水平溢出；分页控件可换行，批量复制按钮可见，console error/warning 为 0。
- 2026-08-29 真实 Browser 验收：15 条目标产品在页面中拆为两列各 15 行，分别复制精确 15 行；`FY01 4866E` 保留空格、`FY024006` 备用码未误收。草稿保存/恢复/更新、X/Escape/取消询问通过；窄屏无溢出，console 0 错误，未提交客户，客户总数保持 77。
- 2026-08-29 真实 Browser 追加验收：50 条名称在前且名称含数字的产品精确拆为编码/名称各 50 行，第 1/25/50 条对应正确；两个复制按钮分别复制精确 50 行，console error/warning 为 0。测试期间未点击创建，健康检查仍为 77 位客户。
- 2026-08-29 真实 Browser 针对带价格/日期表格补验：用户消息中实际可见 18 条记录，修复前识别 15 条，修复后 18/18；原漏行的主编码/名称均正确，编码和名称复制各 18 行，备用编码未误收，console error/warning 为 0，未点击创建客户。
- 2026-08-31 真实 Browser 编辑功能验收：编辑弹窗 16 个关键输入区域全部可见并回填；Alibaba 公司保持非必填；使用合成产品原文点击显式重拆分后得到编码/名称各 2 行。随后取消并重新进入编辑，原值完整恢复，未点击保存、未改变客户数据。390×844 单列布局无横向溢出，console error/warning 为 0；启动时健康检查为 80 位客户。
- 2026-08-31 主 Agent 真实 Browser 长详情验收：目标客户内部编码、批量产品名称、产品原文各 40 条，默认各显示 15 条并提示展开剩余 25 条；三块展开为 40 条、收起为 15 条，关闭重开恢复收起。详情复制编码/名称均为完整 40 行；新增/编辑自定义标签输入可见，未保存或创建客户，草稿数保持 0。
- 同次 390×844 视觉验收发现详情标题挤压导致弹窗内部横向滚动，记录为 `CRM-UI-001` 并修复为弹性可收缩标题容器；复测 `.dialog-frame` 与 `.dialog-header` 的 `scrollWidth == clientWidth`，页面无横向溢出，两个复制按钮可见，console error/warning 为 0。
- 2026-08-31 姓名优先主 Agent Browser 验收：Alibaba 卡片和邮件卡片均以联系人姓名为主标题、公司为副标题；联系人为空的邮件客户回退公司。抽查邮件详情时 dialog 标题为姓名，基本资料同时显示公司和联系人，console error/warning 为 0，未保存或修改客户数据。
- 独立审核子 Agent 尝试复核姓名优先展示，但原浏览器连接中断，按技能恢复后无可用浏览器，记为 `CRM-A2A-002`；本地健康接口正常。该事件不覆盖主 Agent 已完成的真实 Browser 验收。
- 2026-09-01 多列产品表格主 Agent Browser 验收：用户 10 行完整样例显示“识别 10 项产品”，编码/名称各 10 行并按原顺序对应；后续性别、浓度、香调和说明均被忽略。独立审核发现数字产品名/后续字母数字列冲突后已修复；页面追加 3 条刁钻样例正确输出 `SL-001 / Rose 2024 Blend`、`ALI-0001 / Aroma Blend 01`、`SL-002 / Cedar Oil`，第三列后的 `G2 / Floral 2026 / A1 note` 未参与识别。空名称 Tab 样例页面输出 `SL-001` 与空名称，`GENDER / Floral` 未左移混入。取消选择“不保存”后草稿仍为 0，未创建/修改客户。自动化 38/38、Python 编译、JavaScript 语法和 `git diff --check` 均通过。
- 2026-09-01 Git 本地数据隔离验收：本地 `HEAD` 与 `origin/main` 引用一致，当前树和现有历史均无 `clients`/`leads` 路径；新增 8 类本地数据忽略规则，`git check-ignore` 全部命中，`git add --dry-run -A` 不包含受保护路径，Git 索引中受保护文件为 0。本地客户/线索文件数量核验前后不变，未删除或移动数据；完整自动化 40/40 通过。
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

`CRM-OK-001`、`CRM-STARTUP-001`、`CRM-REQUEST-001`、`CRM-VALIDATION-001`、`CRM-PARSE-001`、`CRM-LOAD-001`、`CRM-WRITE-001`、`CRM-NOTFOUND-001`、`CRM-API-001`、`CRM-PRODUCT-PARSE-001`、`CRM-CONTACT-PARSE-001`、`CRM-BULK-PRODUCT-PARSE-001`、`CRM-BULK-COPY-001`、`CRM-DRAFT-001`、`CRM-CHECKLIST-001`、`CRM-PAGINATION-001`、`CRM-UI-001`、`CRM-LAUNCH-001`、`CRM-LAUNCH-002`、`CRM-LAUNCH-003`、`CRM-GIT-001`、`CRM-DATA-ISOLATION-001`、`CRM-UNEXPECTED-001`。含义及 API 行为详见 `README.md`。

## 已知问题 / 审核注意

- **CRM-UI-001 已验证修复：** 新增客户 X、取消、遮罩和 Escape 现统一进入草稿退出门禁；空表单直接关闭，有修改时询问是否保存，客户总数不变。
- 草稿按浏览器源隔离；测试草稿位于独立 `127.0.0.1:8766` 测试源，不影响生产 `127.0.0.1:8765`。
- 详情原始档案只在展开后展示；索引/pipeline-only 客户在首次编辑时才会补建详情 Markdown。
- pipeline 的已有客户按原表位置更新；若手动改变等级，记录字段会同步，但不会自动重排到另一分级表。
- 日志是追加式 JSONL，若目录无写权限，日志器只向 stderr 报告，不应阻断 CRM 主流程。
- 桌面批处理中的 Python 路径优先使用当前 Codex 运行时，找不到时回退到 PATH 中的 `python`。
- 双板块、产品 debounce、批量字段和复制按钮已在最终 Browser 补验中通过；历史 Browser 不可用事件保留为 `CRM-A2A-002`，不再阻塞当前版本交接。
- P1 `CRM-BULK-COPY-001` 已完成真实剪贴板复核：12 行编码/名称分别精确复制，缺失侧空占位行保持不变。复制 fallback 仍会在浏览器拒绝权限时提示手动复制。
- **CRM-LAUNCH-001 历史问题已修复：** 原 BAT 为 UTF-8 无 BOM + LF，且直接使用 `start ... /b`，在真实 `cmd.exe` 中触发路径/`/b` 解析错误；现改为 ASCII + CRLF BAT，仅调用同目录 PowerShell 启动器。首次重试还发现并修复 Windows PowerShell 5.1 不支持 `New-Item -LiteralPath` 的兼容性问题。
- **分页已完成 Browser 复核：** 邮件 76 条默认 12 张/页共 7 页，上一页/下一页、末页 4 张、每页 24/48、筛选/渠道回第一页、ARIA 当前页和窄屏布局均通过。
- **P2 `CRM-PAGINATION-001` 浏览器复现与修复：** 阿里 1 条或搜索命中 1 条时，`renderPagination` 设置边界按钮 `hidden=true`，但 `.page-button { display:inline-grid; }` 覆盖 UA 隐藏规则，主审实测上一页/下一页仍可见；已补 `.page-boundary[hidden] { display:none; }` 及静态断言。主审已通过邮件 76 条→7 页、next/last、24→4 页、48→2 页、筛选回第一页、批量 12 条、复制 12 行、空行精确保留、manual 保护和取消后总数 77；两个审核子 Agent 的浏览器会话分别因浏览器阻塞/额度失败记为 `CRM-A2A-002`，最终由主 Agent Browser 补验，未改真实客户数据。
- 长产品字段以“非空逻辑行”计算 15 条阈值；复制仍使用原始换行字段，因此缺失侧的空占位行不会被详情预览过滤规则影响。
- 每日清单错误提示使用 `CRM-CHECKLIST-001`；该码代表浏览器 `localStorage` 读取或保存失败，不代表客户 API 或客户档案写入失败。审核建议已补登记。

## 回滚指引（仅记录步骤，不在此执行）

1. 停止正在运行的本地 CRM 服务。
2. 备份当前 `ai-assistant/crm-dashboard/`、`ai-assistant/clients/`、`ai-assistant/leads/pipeline.md` 与 `logs/`。
3. 根据项目版本控制或用户指定的安全副本，恢复本次新增的 CRM 看板代码文件；不要直接删除或移动客户主数据。
4. 如需撤销某次客户新建/编辑，先由用户确认目标 `client_id`，再人工恢复对应 Markdown、索引行和 pipeline 行。
5. 重新运行 README 中的测试和健康检查，确认恢复后的三源数据可读。
