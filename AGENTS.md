# llmwiki-study 总控 Agent 规则 (Root AGENTS.md)

> 本文件是仓库级总控规则，约束 `llmwiki-study` 下所有子系统的边界。
> 各子系统内的 `AGENTS.md`（`ai-assistant/AGENTS.md`、`llm-wiki-mvp/AGENTS.md`）继承并细化本规则，冲突时以本文件为准。

## 1. 项目定位

Jason 的**香精油 / 香水油外贸 AI 工作流**总仓库。多子系统共存，核心矛盾是"知识"与"产出"的归属。本文件用硬性边界防止子系统互相污染。

## 2. 子系统职责边界表

| 目录 | 职责 | 可写范围 | 外部只读 |
|---|---|---|---|
| `llm-wiki-mvp/` | 产品 / 价格 / 客户知识库 + 报价话术 | 自身 `wiki/ raw/ output/`（按 `llm-wiki-mvp/AGENTS.md`） | 不读 `ai-assistant` |
| `ai-assistant/` | 获客开发：线索 → ICP → 开发信 → 报价衔接 | 自身全部目录 | 只读 `llm-wiki-mvp/wiki` |
| `docs/` | 系统设计文档（`superpowers/specs`） | 自身 | — |
| `outputs/` | 跨系统临时成品（如合并报价 xlsx） | 自身 | — |
| `remotion/` | 视频渲染框架项目，**与外贸系统无关**，独立维护 | 自身 | — |
| `新建文件夹/` | 待整理杂项，非系统目录 | 自身 | — |

## 3. 硬性边界规则（所有 agent 必须遵守）

1. **知识归 wiki** — 香精专业知识（稀释比例、变色原理、熟化、储存、产品特性、合规规则等）只存 `llm-wiki-mvp/wiki/concept/`，**不得整篇复制到 `ai-assistant/output`**。
2. **产出归 outreach** — `ai-assistant/output/outreach/` 只放**基于 wiki 知识的沟通产出**（客户快捷语、开发信序列、介绍话术）。内容应"引用知识"而非"复制知识"。
3. **子系统互不污染** — `ai-assistant` 不写 `llm-wiki-mvp`；`llm-wiki-mvp` 不读 `ai-assistant` 的 CRM 数据。
4. **报价衔接只读** — 报价时 `ai-assistant` 只**只读** `llm-wiki-mvp/wiki`，结果默认写入 `ai-assistant/output/`。
5. **回织流方向单一** — 正确流向是 `output → wiki/concept`（高价值通用知识经人工审核后回写），**禁止反向把 wiki 已有知识整篇抄进 output**。
6. **删除 / 移动前确认** — 任何删除或移动操作，执行前必须向用户确认（即使是本会话刚生成的文件）。

## 4. 总 Agent 读写约束

- **允许**：在用户明确指令下读写任意子系统。
- **默认**：生成新文件时，先判定"这是知识还是产出"，落到对应目录（见速查表）。
- **禁止**：
  - 跨子系统写入污染
  - 把 wiki 知识整篇抄到 outreach（"完整版知识文档"模式）
  - 未确认即删除 / 移动文件
  - 在 `remotion/` 与外贸系统之间共享或混写文件

## 5. 文件放置速查

| 要存的内容 | 落到哪 |
|---|---|
| 新香精知识 / 行业规则 / 通用话术素材 | `llm-wiki-mvp/wiki/concept/` |
| 客户快捷语 / 开发信 / 介绍话术（引用 wiki） | `ai-assistant/output/outreach/` |
| 报价单 | `llm-wiki-mvp/output/quotes/` 或 `ai-assistant/output/`（按上下文） |
| 客户建档 / ICP / pipeline | `ai-assistant/clients/`、`ai-assistant/leads/` |
| 系统设计说明 | `docs/superpowers/specs/` |
| 跨系统临时成品 | `outputs/` |

## 6. 验收标准（判断 agent 是否越界）

- [ ] 知识类文档只出现在 `wiki/concept/`，不在 `outreach/`
- [ ] `outreach/` 文件只引用 wiki 知识，不含整篇知识复制
- [ ] 子系统间无越权写入（ai-assistant 不碰 wiki 写入，wiki 不读 CRM）
- [ ] 删除 / 移动操作前已向用户确认
- [ ] 报价带内部编码 + 日期，符合 `llm-wiki-mvp/AGENTS.md` 价格规则
- [ ] 客户可见文本为纯文本（无 markdown / emoji / 特殊符号），符合第 7 节格式铁律

## 7. 客户通讯文本格式铁律（2026-09-06 生效）

**任何要发给客户、或用户要复制粘贴走的文本（WhatsApp / 邮件 / 聊天工具 / 开发信），必须纯文本输出。**

- 禁止：markdown 标记（`**粗体**`、`#`、表格线、``` 代码围栏）、emoji、⚠️ 🎭 → 等特殊符号
- 原因：WhatsApp 不解析 `**粗体**`（WhatsApp 用单 `*` 表示斜体），双星号会原样显示成一坨星号，用户复制过去还得手动删
- 正确做法：用「换行 + 空行 + `1. 2. 3.` 编号 + 短横线 `-` + 全大写词」做层级和强调
- `→` 用 `-` 代替；破折号用 `-`
- 中文内部分析 / 与用户闲聊可以俏皮用 emoji（用户喜欢），但**一涉及"要发给别人"或"要复制"立刻切纯文本模式**
- 判断不了就先问："这段是发给客户还是内部看？"
- 用户原话："别天天花里胡哨的"

## 8. 已知边界事故（复盘）

- **2026-08-07**：曾在 `ai-assistant/output/outreach/` 创建 `香皂测试引导完整版.md`，整篇复制 `wiki/concept/product_knowledge.md` 的香精知识 → **已删除**。根因：混淆"知识"与"基于知识的产出"。
- **2026-08-06**：`soap_fabe_intro.md` 含产品知识，其知识已回织 `wiki/concept/fabe_company_intro.md` → **outreach 那份话术版已删除（2026-08-08）**，知识以 wiki 为准。

## 9. AWR 项目台账

- 本仓库启用 AWR；源码台账为 `awr-work-ledger.yaml`，来源配置为 `awr-project.toml`，操作说明见 `docs/AWR_WORKFLOW.md`。
- 开工先在当前 CRM 仓库根目录执行 `awr status --json`，确认项目身份；读取所选任务完整上下文并取得自己的会话认领后再实施，不能复用其他会话的认领。
- 完成任务前实际执行验证，将报告保存在 `docs/verification/`，登记报告哈希、源码内容哈希、命令、范围与时间，再通过 `awr work complete` 按验收项绑定证据。不得仅改 YAML 状态冒充已验证完成。
- 交接前记录下一步、未闭环事项和当前上下文哈希，保存 AWR 检查点。`.awr/` 只用于本地状态，不提交到 Git。
- AWR 不替代 CRM Dashboard 的 A2A 三文件交接门禁，不把计划中的数据库、身份认证、页面或模型接入标成已完成。
