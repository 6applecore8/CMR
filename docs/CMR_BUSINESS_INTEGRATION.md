# CMR 业务接入进度

## 当前完成

- DeepSeek 适配和只读工具已通过合成场景在线测试。模型只规划工具，客户统计和当前价由规则计算；没有向模型发送客户仓储或报价记录。
- `agent_core/demo.py` 使用固定合成客户、固定合成报价和演示角色；不是实际客户库，也不是网页或正式认证。
- `agent_core/migration_preflight.py` 只读检查旧 CRM 源目录。缺失或损坏返回 UNAVAILABLE，未检查负责人归属、未导入和未生成备份，不能据此批准迁移。
- `agent_core/credentials.py`、`agent_core/auth.py` 提供独立密码、会话、角色刷新、CSRF 和单进程限流规则。内存仓储只适合开发验证；不是实际登录接口，也没有保护旧服务。
- `agent_core/migrations/V001__business_foundation.sql` 是 PostgreSQL 迁移候选，不会自动执行，尚未在真实 PostgreSQL 验证。它不等于可部署的数据库服务：用户管理、报表仓储、RLS、事务、审批、审计实现与验证仍需完成。

## 本地合成演示

下面每条 `--live` 请求会调用 DeepSeek 并产生费用。仅向模型发送预定义的合成问题，不读取真实客户或 Wiki。需先在同一个 PowerShell 进程加载本机加密密钥：

```powershell
cd D:\Code\CMR
.\scripts\deepseek-secret.ps1 -Action Load
$env:PYTHONPATH = (Join-Path (Get-Location) 'ai-assistant')
python -m agent_core.demo --sample tier --role sales --live
python -m agent_core.demo --sample tier --role manager --live
python -m agent_core.demo --sample price --role sales --live
```

演示日期固定在 2026-07-15，演示客户、产品和金额均为虚构内容。真实价格必须依照业务时钟、可用的实际主数据、组织权限及版本政策计算。

## 检查旧数据（未来在来源机器执行）

在拥有资料的电脑指定其 `ai-assistant` 根目录执行；仅做只读可读性检查，不保存输出文件、不迁移或修改：

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'ai-assistant')
python -m agent_core.migration_preflight --root 'D:\your-source\ai-assistant'
```

报告不显示客户名字、地址、文件名或正文。`READABLE_REQUIRES_REVIEW` 只表示指定文件可读，仍须人工核对完整性、备份、导入预演和每位客户的归属；`migrationAllowed` 固定为 false。缺失、文件损坏或读取失败不可当作零个客户。

## 尚未完成

1. 客户主源位于另一台电脑；需要确认来源路径、备份和归属分配，不自动拷贝或切换主源。
2. 当前设备的 Docker 服务未运行，PostgreSQL 工具和 Python 驱动未发现；迁移尚未连接真实数据库或执行 SQL。
3. 登录/会话规则尚未接入 HTTP，旧 CRM 所有接口仍未鉴权。不要绑定外网或让他人访问。
4. 报价和政策仓储、事务审批、角色管理、全接口授权、审计、持久化和真实数据库并发测试仍待实现。
5. 业务员/管理者网页、问数入口、Wiki 只读检索与 RAG，以及真实浏览器/多账号验收仍待完成。

原有 CRM 的客户文件和 Wiki 均未被移动、删除、写入或迁移，本轮未推送 GitHub。