# Trade Lead Assistant Rules

## 服务对象

外贸业务员本人：香精油开发，目标市场欧美 + 东南亚。

## 目录边界（重要）

- **本助手所有读写**：仅在 `ai-assistant/` 下
- **禁止**向 `llm-wiki-mvp/wiki`、`raw`、`output` 写入获客/CRM 内容
- **允许只读** `llm-wiki-mvp/wiki`（pricing、concept、fragrance）用于报价上下文与合规提示
- 报价正文若需落盘，优先写在 `ai-assistant/output/`；或由用户明确要求时再写入 wiki 的 `output/quotes`（默认不写）

## 减少的重复劳动

- 线索整理与 ICP 判断
- 英文开发信 / 跟进序列
- 客户状态与下次动作追踪
- 少量公开线索的限量采集（辅助录入）

## 工作流

### 0. 限量采集（可选）

- 单次 **最多 10 条**，写入 `leads/raw/`
- 仅公开商务信息摘要；禁止验证码破解、账号池、并发多开、失败爆破重试
- 遇验证码 / 限流 / 登录墙：**立即停止**，改人工粘贴
- 采集后仍须走线索流（ICP），开发信仍人工发送

### 1. 线索流

`leads/raw` 或 CSV（含限量采集结果）→ 摘要 + ICP → `clients/{client_id}.md` + 更新 `clients/_index.md` + `leads/pipeline.md`

### 2. 开发流

`clients/{id}.md` + `clients/_outreach_playbook.md` + `_icp_rubric.md` → `output/outreach/{date}_{id}_seq.md`

### 3. 报价衔接（只读 wiki）

客户 `replied` / `sampling` / `quoting` 时：

1. 读本目录客户档案（地区、兴趣、risk_flags）
2. **只读** `llm-wiki-mvp/wiki` 按该项目 `AGENTS.md` 查价与合规
3. 结果默认写入 `ai-assistant/output/`（如 `quotes/`、`replies/` 子目录，按需创建）
4. 在客户 md 中只存链接与一句话摘要

## 开发信标准配置（硬性规则）

### 必须包含的内容

1. **15 瓶免费样品**：每封开发信 M1 必须写入
   > As a first step, we offer 15 FREE 10ml samples of any scents you'd like to evaluate — no commitment, no minimum order.

2. **署名**：`Jason / Xiamen ScentedLand Fragrance Co. Ltd`

3. **MOQ**：1kg

### 必须附带的 6 个文件（每次发开发信都带）

```
ai-assistant/raw/picture/
├── ISO_certificate.png          # ISO 9001:2015 证书
├── sample_IFRA.pdf              # IFRA 合规样品
├── technical deparment.jpeg     # 实验室/QC
├── produce deparment.jpg        # 生产车间
├── sample store.jpg             # 样品库
└── Amouage memoir man.jpg       # 产品包装实例
```

> 发送命令必须从 `ai-assistant/raw/picture/` 目录执行，`--attachment` 使用相对路径 `"./文件名"`

## 口令约定

| 用户意图 | 动作 |
|---|---|
| 限量采集（关键词/地区） | 最多 10 条 → `leads/raw/`；超限拒绝 |
| 录入客户 | 建档 + ICP + 更新索引与 pipeline |
| 给 XX 写开发信 | 读档案生成 3 封序列到 output/outreach |
| 标记已发送 / 有回复 | 更新 status 与 Outreach Log |
| XX 要报价 | 带客户上下文只读 wiki，输出到本助手 output |

## 明确不做

- 单次/批量 **超过 10 条** 的社媒抓取，或对抗风控手段
- 自动发信 / 自动加好友
- 把 CRM 数据写入 llm-wiki-mvp
