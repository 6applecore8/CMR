# Agent 领域规则：阶段一

这里是可运行的领域规则和契约，不是新服务，也未给现有 CRM 增加登录。

已实现：同组织/负责人范围的客户只读工具、严格参数、精确十进制价格、版本与时效规则、管理政策权限及版本冲突检查。

尚未实现：登录、PostgreSQL 仓储、HTTP 集成、双角色页面、审核与审计持久化、真实模型、Wiki/RAG。不要把领域测试通过描述成这些功能已上线。

## 测试

在仓库根目录运行：

```text
python -m unittest discover -s ai-assistant/agent_core/tests -v
python -m unittest discover -s ai-assistant/crm-dashboard/tests -v
```

测试仅使用合成记录，不读取真实客户目录，不调用网络或付费模型。

## 安全与数据约定

- Principal 必须由未来后端认证层创建；Python 对象不是认证机制。
- 工具不接受 tenantId、ownerId、role、sql 或 asOf，分页最大 50。
- 客户搜索先做权限筛选，列表不带地址，详情仅返回明确字段。
- 仓储故障向上传递，不能被捕获后返回正常 count=0。
- 当前报价必须带产品、规格、币种、单位、贸易条款与数量；客户专价先检查客户权限。
- 数量区间及有效期均左闭右开；金额与数量使用 Decimal，响应金额是十进制字符串。
- 草稿和未来版本不能替代当前价。最新已发布价过期/撤回时，不回退更旧版本。
- 重叠档位、并列版本和无效替代关系返回 REVIEW_REQUIRED，currentPrice 为 null。
- minimum_year 是新版本的发布日期门槛；旧价复核需发布新的版本，不能改写历史记录。
- 角色和政策变更在本包中只产生快照，未来必须用数据库事务、并发校验和审计保存。
- 原有 CRM 仍是未鉴权的本机工具，不能因存在此包就对外部署。

完整分阶段计划见 docs/superpowers/specs/2026-10-26-agent-workbench-plan.md。
