# 外贸 AI 开发助手（Trade Lead Assistant）

独立于 `llm-wiki-mvp` 的获客与开发助手，避免污染知识库 wiki。

## 与 wiki 的关系

| 本目录 | `llm-wiki-mvp` |
|---|---|
| 线索、客户档案、开发信、助手规则与代码 | 产品知识、报价、话术、合规 |
| 读写本目录文件 | **只读**引用 wiki（报价/合规时） |

设计说明：`docs/superpowers/specs/2026-07-30-trade-lead-assistant-design.md`  
（仓库根目录 `docs/`，与实现目录分离。）

## 目录结构

```text
ai-assistant/
├── README.md
├── AGENTS.md                 # 助手工作规则
├── leads/                    # 线索原始输入
│   ├── raw/
│   ├── import_template.csv
│   └── pipeline.md
├── clients/                  # 客户档案（轻量 CRM）
│   ├── _index.md
│   ├── _icp_rubric.md
│   ├── _outreach_playbook.md
│   └── _client_template.md
├── output/
│   └── outreach/             # 生成的开发信 / 跟进序列
└── src/                      # 后续脚本与代码
```

## 主流程

```text
限量采集≤10 或 人工粘贴/CSV → leads/raw
  → 摘要 + ICP
  → clients/{client_id}.md
  → output/outreach/
  →（有需求时只读）llm-wiki-mvp/wiki 报价与合规
```

## 合规与限量采集

- 允许**单次最多约 10 条**公开线索的限量采集，结果进 `leads/raw/`
- 禁止超量抓取、自动群发、破解验证码/绕过登录
- 开发信只生成，人工确认后发送
- 平台 ToS 与账号风险自负；限量不保证不被风控
