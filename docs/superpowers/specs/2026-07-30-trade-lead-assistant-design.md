# 外贸 AI 开发助手（Trade Lead Assistant）设计说明

## 1. 目标

为香精/香水外贸业务员搭建一个**合规、可落地**的 AI 获客与开发助手，覆盖：

- 线索录入与客户档案（轻量 CRM）
- ICP 筛选与优先级打分
- 英文开发信 / 跟进序列生成
- 与现有 `llm-wiki-mvp` 产品知识、报价、话术打通

**核心价值**：减少「找客户 → 判断值不值得跟 → 写第一封信 → 持续跟进 → 报价」过程中的重复劳动，而不是做成自动爬虫或群发机器人。

## 2. 服务对象与市场

| 项 | 说明 |
|---|---|
| 服务对象 | 用户本人（单人使用，不做团队权限） |
| 产品 | 复合香精油（Fragrance Oils / Compound Fragrance） |
| 目标市场 | **欧美** + **东南亚** |
| 典型客户类型 | 香水品牌、蜡烛/香氛家居、个人护理 OEM、分销商、电商卖家 |

### 2.1 市场差异（影响 ICP 与话术）

| 维度 | 欧美 | 东南亚 |
|---|---|---|
| 合规重点 | EU 限用成分、USA/CA Prop 65、Phthalate-free、IFRA | 部分国家关注 Halal；法规相对分散 |
| 沟通风格 | 简短专业、价值/合规先行 | 关系导向、可稍暖、强调样品与配合度 |
| 常见切入 | 替代大牌/高性价比配方、无 DEP、可定制 | 热销香型、小单灵活、快速打样 |
| 参考知识 | `wiki/concept/compliance_rules.md` | 同上 + Halal 相关说明 |

## 3. 合规边界与限量采集（第一版）

### 3.1 明确不做

- **大批量**爬取（单次/单日远超限量上限）
- 自动加好友、批量私信、绕过登录墙/验证码、伪造设备指纹等对抗手段
- 未经同意批量采集个人隐私向的邮箱/电话（非页面已公开的商务联系方式）
- 伪装身份或诱导披露非公开联系方式
- 将采集能力做成无人值守 7×24 跑数

### 3.2 限量采集（本版新增，其余模块不变）

业务上需要**少量**社媒公开信息辅助建档，本版允许「限量采集」，硬约束如下：

| 约束 | 规则 |
|---|---|
| **单次上限** | **≤ 10 条**线索/档案（默认 10，可配置但不得默认调高） |
| **频次** | 建议每日 ≤ 1–2 次任务；任务间人工间隔，禁止并发多开 |
| **目标** | 仅用户指定的关键词/地区/岗位下的**公开**公司或个人商务主页摘要 |
| **字段** | 公司名、职位、地区、公开简介摘要、公开主页 URL；**不**为扩列而挖隐藏联系方式 |
| **落盘** | 原始结果只进 `ai-assistant/leads/raw/`，再走既有 ICP → clients 流程 |
| **人工** | 每次任务前确认搜索条件；采集后人工抽查再开发信 |
| **风险自负** | 社媒平台 ToS 可能限制自动访问；限量仅为降低风控概率，**不保证**不被限制，也不构成法律意见 |

#### 3.2.1 采集在主流程中的位置

```text
（可选）限量采集 ≤10 条  →  leads/raw/
        或人工粘贴 / CSV
              ↓
        摘要 + ICP → clients/ → output/outreach/
```

CRM、ICP、开发信、报价衔接等**其它设计不变**；采集只作为线索入口之一。

#### 3.2.2 实现原则（`src/` 后续编码时）

- 配置项：`max_items=10` 写死校验，超出直接拒绝执行
- 优先：用户导出文件、官方/许可工具、浏览器由用户登录后的**受控**辅助（非绕过验证）
- 请求之间加较长间隔；失败（验证码/429）即**停止**，不自动重试爆破
- 不实现：验证码破解、账号池、IP 轮换对抗、隐藏 API 逆向扩量

### 3.3 允许的数据来源（汇总）

| 来源 | 方式 | 备注 |
|---|---|---|
| LinkedIn 等社媒 | **限量采集 ≤10** 或人工复制公开简介 / 官方导出 | 采集结果进 `leads/raw` |
| 展会名录 | 用户导入 Excel/CSV | Cosmoprof、Beautyworld 等 |
| 公司官网 | 用户粘贴或单页少量抓取公开 About/Contact | 计入当次 10 条额度更稳妥 |
| Alibaba / 展会交换名片 | 手动录入 | — |
| 老客户 / 转介绍 | 手动录入 | — |
| 客户主动询盘 | 邮件/WhatsApp 粘贴 | 进入跟进流 |

### 3.4 隐私原则

- 客户档案默认仅本地/用户自有目录存储
- 不向第三方上传完整客户列表（除用户明确使用的 LLM API 请求外）
- 发送开发信前必须**人工确认**（AI 只生成，不自动发信）
- 限量采集数据仅用于本人开发，不转售、不批量外泄

## 4. 与现有 llm-wiki-mvp 的关系

现有体系：

```text
raw/ → wiki/ → output/
```

本助手**独立目录**存放，**不写入** `llm-wiki-mvp`，避免污染 wiki；需要产品/报价/合规时**只读**引用 wiki：

```text
ai-assistant/                 # 助手根目录（与 llm-wiki-mvp 并列）
├── leads/raw/                # 线索原始输入
├── clients/                  # 客户档案、ICP、沟通要点
├── output/outreach/          # 开发信、跟进序列
├── output/quotes|replies/    # 可选：助手侧报价/回复草稿
├── src/                      # 脚本与代码
└── AGENTS.md

只读 → llm-wiki-mvp/wiki/     # pricing、concept、fragrance
```

| 现有 wiki 能力 | 本助手如何复用 |
|---|---|
| `wiki/pricing/` + 报价规则 | **只读**；客户有兴趣后生成报价草稿（默认写入 `ai-assistant/output/`） |
| `wiki/concept/sales_scripts.md` | **只读**跟进与异议处理模板 |
| `wiki/concept/compliance_rules.md` | **只读**；欧美开发信合规卖点 |
| `wiki/concept/product_knowledge.md` | **只读**；个性化切入点 |
| 助手 `AGENTS.md` | 线索流 + 开发流；禁止写回 wiki |

## 5. 第一版范围（完整 MVP，但仍是最小可用）

### 5.1 要做的四个模块

1. **线索录入与客户档案（轻量 CRM）**
2. **ICP 筛选打分**
3. **开发信 / 跟进序列生成**
4. **报价与产品知识对接（调用现有 wiki，不重复造报价引擎）**

### 5.2 第一版明确不做

- **超量**爬虫或社媒大规模同步（单次默认硬顶 10 条；官方授权 API 另议）
- 自动发邮件 / 自动 LinkedIn 私信
- 验证码破解、账号池、指纹伪造等对抗风控手段
- 多用户、权限、云端 SaaS
- 复杂前端（可先 Markdown/CSV + 脚本；Web 为二期）
- 完整邮件追踪像素、打开率统计
- 支付/合同/物流全链路

## 6. 用户主流程

```text
① 获取线索
   · 方式 A：限量采集（≤10 条）→ leads/raw/
   · 方式 B：人工 LinkedIn/展会/官网粘贴或 CSV
        ↓
② 进入助手清洗（公司名、职位、地区、公开简介、已知邮箱）
        ↓
③ AI：清洗 → 客户摘要 → ICP 打分 → 建议动作
        ↓
④ 用户确认优先级，生成开发信（英文，分市场风格）
        ↓
⑤ 用户人工发送（邮件 / LinkedIn / WhatsApp）
        ↓
⑥ 有回复 → 记入沟通要点 → 生成跟进信 / 询盘要点
        ↓
⑦ 进入样品或报价 → 只读 wiki 报价/合规，草稿默认在 ai-assistant/output
```

## 7. 模块设计

### 7.1 模块 A：线索录入与客户档案

#### 输入方式

- **单条粘贴**：文本框/Markdown 模板（LinkedIn About、公司介绍）
- **批量导入**：CSV（字段见下）
- **从询盘粘贴**：邮件正文 → 抽取公司与需求

#### 客户档案字段（第一版）

| 字段 | 必填 | 说明 |
|---|---|---|
| `client_id` | 自动 | 如 `2026-07-30_acme_fragrances` |
| `company` | 是 | 公司名 |
| `contact_name` | 否 | 联系人 |
| `title` | 否 | 职位（Buyer / Founder / R&D） |
| `country_region` | 是 | 国家/地区；用于市场桶：EU/US / SEA |
| `market_bucket` | 自动 | `EU_US` \| `SEA` \| `OTHER` |
| `channel_type` | 建议 | brand / distributor / oem / candle_home / ecommerce / unknown |
| `source` | 是 | linkedin / exhibition / website / alibaba / referral / inbound |
| `public_summary` | 否 | 用户粘贴的公开简介原文 |
| `known_email` | 否 | 仅用户已知的商务邮箱 |
| `known_phone` | 否 | 可选 |
| `product_interest` | 否 | 香型/品类兴趣 |
| `icp_score` | 自动 | 0–100 |
| `icp_tier` | 自动 | A / B / C |
| `status` | 是 | 见状态机 |
| `next_action` | 否 | 下次动作与日期 |
| `notes` | 否 | 人工备注 |
| `created_at` / `updated_at` | 自动 | 日期 |

#### 跟进状态机

```text
new → researched → outreach_1 → outreach_2 → outreach_3
        ↓              ↓            ↓
     disqualified   replied → sampling → quoting → won / lost
                         ↘ cold（长期无回复，可再激活）
```

| 状态 | 含义 |
|---|---|
| `new` | 刚录入 |
| `researched` | 已摘要 + ICP |
| `outreach_1/2/3` | 第 1/2/3 次触达已发出（人工标记） |
| `replied` | 有回复 |
| `sampling` | 寄样中 |
| `quoting` | 报价中 |
| `won` / `lost` | 成交 / 明确放弃 |
| `disqualified` | ICP 不合格 |
| `cold` | 触达后长期无回复 |

#### 存储形态（第一版）

**独立于 wiki 的文件型 CRM**，全部在 `ai-assistant/`：

```text
ai-assistant/
├── leads/
│   ├── raw/                    # 原始粘贴、导入 CSV
│   ├── pipeline.md             # 看板摘要
│   └── import_template.csv
├── clients/
│   ├── _index.md               # 客户索引 + 分数 + 状态
│   ├── _icp_rubric.md
│   ├── _outreach_playbook.md
│   ├── _client_template.md
│   └── {client_id}.md          # 单客户档案
├── output/
│   └── outreach/               # 开发信、跟进序列
├── src/                        # 代码
└── AGENTS.md
```

单客户文件建议结构：

```markdown
# {Company} — {Contact}

## Profile
- market_bucket / country / channel_type / source
- icp_score / tier / status / next_action

## Public Summary
（用户粘贴原文压缩后）

## ICP Rationale
（打分理由）

## Outreach Log
| date | channel | template | result |

## Communication Points
- ...

## Product / Quote Links
- 关联 output/quotes/...
```

### 7.2 模块 B：ICP 筛选打分

#### 理想客户画像（香精外贸）

**加分信号**

| 信号 | 分值示例 | 说明 |
|---|---|---|
| 明确做成品香水/香氛/蜡烛/个护 | +25 | 需求匹配 |
| 有自有品牌或 OEM 产线 | +15 | 持续采购可能 |
| 欧美：提到合规、IFRA、private label | +10 | 专业买家 |
| 东南亚：分销网络或电商体量 | +10 | 放量可能 |
| 采购/创始人/R&D 决策相关职位 | +10 | 触达有效 |
| 已知商务邮箱或展会面对面 | +10 | 可触达 |
| 与现有热销香型/客户类型相似 | +10 | 转化路径清晰 |

**减分 / 淘汰信号**

| 信号 | 处理 |
|---|---|
| 纯个人消费者、无公司 | 直接 C 或 disqualified |
| 只做成品零售且无采购权（店员） | 低分 |
| 竞品香精厂（非潜在合作） | 人工判断，默认低优 |
| 无法判断国家与业务 | 待补充信息，暂不 outreach |

#### 分档

| Tier | 分数 | 动作 |
|---|---|---|
| **A** | 70–100 | 优先写个性化开发信，3 日内触达 |
| **B** | 40–69 | 标准模板 + 轻度个性化，批量跟进 |
| **C** | 0–39 | 仅入库观察，或要求用户补充信息后再评 |

#### 输出

每次评估产出：

1. `icp_score` + `tier`
2. 3–5 条打分理由（中文，给业务员看）
3. `recommended_angle`：建议切入点（合规 / 性价比 / 热销香型 / 小单打样等）
4. `risk_flags`：如「欧美需强调无铃兰醛/无 DEP」

### 7.3 模块 C：开发信与跟进序列

#### 原则

- 默认 **英文**（欧美 + 东南亚 B2B 通用）
- **短**：首封 80–150 词
- **不群发感**：至少 1 处个性化（公司业务、地区、品类）
- **不自动发送**；生成到 `output/outreach/`
- 复用并扩展 `sales_scripts.md` 中的 follow-up 思路

#### 序列（默认 3 封）

| 序号 | 时机（建议） | 目标 |
|---|---|---|
| Mail 1 | Day 0 | 自我介绍 + 一个具体价值点 + 轻 CTA（是否方便看 2–3 个样品方向） |
| Mail 2 | Day 5–7 | 补充社会证明或热销场景 + 降低门槛（小样/MOQ 说明） |
| Mail 3 | Day 12–14 | 最后轻触达 + 可选资源（香型列表/合规说明），允许结束 |

#### 市场语气差异

**EU/US 模板侧重点**

- 合规与质量体系一句话带过（IFRA / phthalate-free 按真实能力写，禁止夸大）
- 商业级配方、利润空间、可定制
- CTA 偏「是否值得对比样品」

**SEA 模板侧重点**

- 配合度、打样速度、热销香型
- 可提灵活起订（仍须符合真实 MOQ 政策）
- 语气可略更 friendly，仍保持专业

#### 生成物格式

```text
output/outreach/{date}_{client_id}_seq.md
```

内容包含：

- Subject 行（2 个备选）
- Mail 1 / 2 / 3 正文
- LinkedIn 短消息版（可选，更短）
- 中文「发送前检查清单」（是否夸大合规、是否已改公司名等）

#### 禁止内容

- 虚假认证、虚假大客户名
- 未核实的「100% 等同大牌」表述（可用 inspired / commercial-grade 等合规表述，与现有话术一致）
- 威胁感催促、每日多封骚扰

### 7.4 模块 D：报价与产品知识对接

当状态进入 `replied` / `sampling` / `quoting`：

1. 从客户档案读取：地区、兴趣香型、合规约束
2. 按现有 `AGENTS.md`：**wiki 优先 → raw 兜底** 查价与推荐
3. 欧美客户：优先提示 `compliance_rules`（EU/US）
4. 输出仍写入 `output/quotes/`、`output/replies/`
5. 在客户 md 中增加链接与一句话摘要，避免双处维护正文

**不做**：重写报价引擎；本模块是「编排 + 提醒 Agent 带上客户上下文」。

## 8. Agent 工作流（扩展 AGENTS.md 的约定）

### 8.1 线索流（Lead Flow）

```text
ai-assistant/leads/raw →（摘要 + ICP）→ clients/{id}.md + _index.md + pipeline.md
```

### 8.2 开发流（Outreach Flow）

```text
ai-assistant/clients/{id}.md + _outreach_playbook
  +（只读）llm-wiki-mvp/wiki/concept/*
  → ai-assistant/output/outreach/...
```

### 8.3 与 wiki 的边界

| 流 | 路径 | 写哪里 |
|---|---|---|
| wiki 查询/生产/回织 | 仍仅在 `llm-wiki-mvp` | wiki 自己的规则 |
| **线索流** | leads/raw → clients | **仅** `ai-assistant` |
| **开发流** | clients → output/outreach | **仅** `ai-assistant` |
| **报价衔接** | 只读 wiki → 草稿 | 默认 `ai-assistant/output` |

### 8.4 Agent 操作口令（见 `ai-assistant/AGENTS.md`）

| 用户意图 | Agent 动作 |
|---|---|
| 「录入客户：…」 | 建档 + ICP + 更新索引（写 ai-assistant） |
| 「给 XX 写开发信」 | 读档案生成 3 封序列 |
| 「标记已发送 / 有回复」 | 更新 status 与 Outreach Log |
| 「XX 要报价 …」 | 只读 wiki + 客户上下文，输出默认在助手目录 |

## 9. 技术形态（分期）

### 9.1 一期（本设计对应的实现目标）

- **形态**：独立目录 `ai-assistant/` 内文件 + Agent（Markdown/CSV）
- **代码**：放在 `ai-assistant/src/`，不进入 llm-wiki-mvp
- **可选薄脚本**：CSV 导入、从模板生成客户 md、更新 `_index.md`
- **不强制** Web UI；对话完成「粘贴 → 生成 → 保存」

### 9.2 二期（可选）

- 本地简单 Web（客户列表、状态拖拽、一键复制开发信）
- 邮箱草稿箱集成（仍人工点发送）
- 官方数据源连接器（用户自备 LinkedIn 导出文件）

### 9.3 技术原则

- 与现有目录约定一致，降低切换成本
- 客户数据可读、可 Git 备份（注意：若仓库会分享，客户 PII 勿推远程）
- 先流程正确，再自动化

## 10. 目录与文件清单

```text
ai-assistant/                         # 与 llm-wiki-mvp 并列
├── README.md
├── AGENTS.md
├── leads/
│   ├── raw/
│   ├── import_template.csv
│   ├── pipeline.md
│   └── README.md
├── clients/
│   ├── _index.md
│   ├── _icp_rubric.md
│   ├── _outreach_playbook.md
│   ├── _client_template.md
│   └── (客户文件...)
├── output/
│   └── outreach/
└── src/                              # 助手代码
```

设计文档（不放进 wiki）：

```text
docs/superpowers/specs/2026-07-30-trade-lead-assistant-design.md
```

## 11. ICP 与话术知识文件（写在 ai-assistant/clients，不写 wiki）

### 11.1 `_icp_rubric.md`

固化第 7.2 节加分/减分、分档与 `market_bucket`。

### 11.2 `_outreach_playbook.md`

- EU/US vs SEA 语气、3 封序列、禁止表述、发送前检查
- 跟进/MOQ 等可只读参考 wiki 的 `sales_scripts.md`

## 12. 成功标准（MVP 验收）

| # | 标准 |
|---|---|
| 1 | 粘贴 1 条欧美线索，能生成完整客户 md + ICP 分档 + 理由 |
| 2 | 粘贴 1 条东南亚线索，同上，且切入点与语气区分于欧美 |
| 3 | 对 A 级客户生成 3 封英文序列 + 可选 LinkedIn 短消息，可直接人工发送 |
| 4 | 客户状态可在档案与 `pipeline.md` / `_index.md` 中追踪 |
| 5 | 从「有回复」客户能衔接到现有报价流程，并带上地区合规提示 |
| 6 | 限量采集硬顶 ≤10/次，遇阻即停；全流程无自动发信 |

## 13. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 平台 ToS / 账号风控 | 单次 ≤10、低频、遇验证码即停；不对抗风控；优先人工/官方导出 |
| 开发信同质化被垃圾邮件过滤 | 强制个性化字段；控制日发送量（业务员自律） |
| 合规话术夸大 | 检查清单 + 以 wiki `compliance_rules.md` 为准，不确定则不写 |
| 客户文件泄露 | 本地使用；勿把含邮箱的 clients 推到公开仓库 |
| 与报价知识不同步 | 报价只读 wiki 规则，客户档只存链接与摘要 |

## 14. 建议实施顺序（实现阶段）

1. ~~建 `ai-assistant/` 骨架与规则文件~~（已完成，与 wiki 隔离）  
2. 用 2 个虚构客户（1 欧美、1 东南亚）跑通建档 + 开发信  
3. 按需在 `src/` 加：CSV 导入、**限量采集（max=10）** 入口脚本  
4. 再考虑简易 Web（仍不写入 llm-wiki-mvp）  

## 15. 总结

本助手是 **「限量线索入口（≤10）+ 人工把关 + AI 判断与写作 + 只读复用报价 wiki」**，不是大批量社媒爬虫，也不做自动发信。

**实现与数据全部在 `ai-assistant/`**，与 `llm-wiki-mvp` 隔离；CRM / ICP / 开发信 / 报价衔接设计不变，仅线索获取增加限量采集选项。
