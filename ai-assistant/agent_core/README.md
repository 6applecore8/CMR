# Agent 领域规则：阶段一

这里是可运行的领域规则和契约，不是新服务，也未给现有 CRM 增加登录。

已实现：同组织/负责人范围的客户只读工具、严格参数、精确十进制价格、版本与时效规则、管理政策权限及版本冲突检查。

尚未实现：登录、PostgreSQL 仓储、HTTP 集成、双角色页面、审核与审计持久化、真实模型、Wiki/RAG。不要把领域测试通过描述成这些功能已上线。

2026-10-27 更新：模型提供方改为 DeepSeek，已增加环境变量配置的真实 API 调用适配器和 QueryService 组合入口，离线测试不访问网络。上面的“真实模型未实现”描述的是阶段一交付时状态；目前仍未验证真实 API、未接入旧 Dashboard。配置与显式在线冒烟步骤见 `docs/DEEPSEEK_SETUP.md`，切勿复用聊天中泄露的密钥。

## 测试

在仓库根目录运行：

```text
python -m unittest discover -s ai-assistant/agent_core/tests -v
python -m unittest discover -s ai-assistant/crm-dashboard/tests -v
```

测试仅使用合成记录，不读取真实客户目录，不调用网络或付费模型。

### 可选 PostgreSQL 结构验收

`tests/test_postgres_schema_integration.py` 提供独立数据库的合成数据检查；默认跳过实际数据库部分。运行前需由操作者准备专用 PostgreSQL 测试数据库，数据库名必须符合 `cmr_test_*`，安装 psycopg 3，并在当前进程设置 `CMR_TEST_POSTGRES_DSN`。不要在日志或命令历史中记录连接密码。运行上述领域测试即可包含该检查。

检查会在独立事务中创建随机名称的 schema，验证建表、组织间外键及角色约束，最后回滚；数据库名称不符合要求时在写入前报错。它需要创建 schema 的测试账号，不能代替受限业务账号、并发事务、员工仓储、接口鉴权或客户迁移的验收；运行成功也不表示阶段二完成。

`tests/test_postgres_staff_integration.py` 是另一项单独的隔离集群测试：额外设置 `CMR_TEST_ALLOW_ROLE_CREATION=1` 后，使用管理员连接创建随机测试 schema、合成记录和受限登录角色并提交；这些测试对象有意保留，不会自动删除。受限角色无密码，测试必须运行在无网络的专用临时集群中，不得用于共享或生产环境。测试覆盖员工查询、角色权限、停用会话失效，以及候选会话仓储的保存、过期和撤销。

`session_repository.py` 和 `V002__session_security.sql` 是候选实现，存放令牌及 CSRF 摘要而非明文。新增 `persistent_auth.py` 将会话仓储接入候选认证服务，隔离测试验证了跨实例恢复、CSRF、退出和员工停用；原有 `AuthenticationService` 默认仍为内存会话，两者都尚未接入旧 HTTP 服务。V002 对已有会话行不会自动转换，禁止直接应用到现有业务数据库。登录限流目前仍是进程内实现，并无跨进程共享限流和持久会话总量限制，不可作为生产方案。上线前仍须验证会话竞争、受限账号的部署权限、入口鉴权和 CSRF 保护。

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
