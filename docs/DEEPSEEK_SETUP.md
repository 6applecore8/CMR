# CMR DeepSeek 配置

## 当前范围

2026-10-27 用户将后续模型提供方从千问改为 DeepSeek。本说明覆盖此前阶段规划中的模型选型；旧计划和验收报告保留为历史证据，不改写历史文件哈希。

- 默认模型：`deepseek-flash`，可用 `DEEPSEEK_MODEL` 调整。
- 官方接口：`https://api.deepseek.com/chat/completions`，兼容 OpenAI Chat Completions 请求格式；当前使用标准库 urllib，无须安装 OpenAI SDK。
- 新增 `DeepSeekPlanner`、`create_model_planner` 和 `QueryService`，每次问数仅允许一次模型请求、一个只读工具。
- 仅将用户问题发送给模型，不自动上传客户名单、地址、报价主源、Wiki 或工具查询结果。用户问题本身也可能含隐私，提交前应确认云端处理权限。
- 模型适配和工具组合可供可信后端调用，但旧 Dashboard 没有新增聊天路由或登录。身份、数据库、界面与真实在线联调仍独立验收，不代表网站现在已能问数。

## 密钥安全

聊天中出现过的 Key 应到 DeepSeek 控制台撤销并重建，不要再放进聊天、源码、截图、日志或前端。这里只读取后端进程环境变量，没有内置或文件中的默认密钥。`.env` 与 `.env.*` 已忽略，但代码不自动加载 dotenv 文件。

在仓库根目录打开 PowerShell，将新 Key 通过隐藏输入加入当前进程：

```powershell
$secureKey = Read-Host "New DeepSeek API key" -AsSecureString
$env:DEEPSEEK_API_KEY = [System.Net.NetworkCredential]::new('', $secureKey).Password
$env:CMR_LLM_PROVIDER = 'deepseek'
$env:DEEPSEEK_MODEL = 'deepseek-flash'
$env:DEEPSEEK_TIMEOUT_SECONDS = '30'
$env:DEEPSEEK_MAX_TOKENS = '1024'
```

不使用 `setx` 保存明文，不把 Key 写进启动脚本。上述变量只影响当前终端及其子进程；将来的后端服务需由部署平台注入相同变量。结束后可执行 `Remove-Item Env:DEEPSEEK_API_KEY` 清除当前环境变量。

## 显式在线测试

这一步会调用一次真实 API 并计费。本次开发仅执行了离线测试，没有使用聊天中暴露的 Key，也没有声称验证过余额或连通性。

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'ai-assistant')
python -m agent_core.deepseek_smoke
```

该命令只发送固定的合成统计问题，显示选中的工具和参数，不访问任何客户仓储。它只验证 API 工具规划；不证明对真实业务数据的问数已上线。

## 可信后端组合

```python
from agent_core.deepseek import create_model_planner
from agent_core.query_service import QueryService

# dispatcher 必须连接受控仓储；principal 来自未来的后端认证层。
service = QueryService(create_model_planner(), dispatcher)
response = service.ask(question, principal, server_generated_trace_id)
```

不要从请求或模型参数构造 `Principal`。不要把这个服务直接挂到旧的未鉴权 HTTP 路由。统计、搜索、详情和价格由 `ToolDispatcher` 及领域规则校验，模型不能修改角色、组织、查询时钟、SQL 或报价有效性。

## 错误与日志

- 缺少 Key：`MODEL_NOT_CONFIGURED`；无效配置：`MODEL_CONFIG_INVALID`。
- 401/403：`MODEL_AUTH_FAILED`；402：`MODEL_BALANCE_INSUFFICIENT`；429：`MODEL_RATE_LIMITED`。
- 超时：`MODEL_TIMEOUT`；网络失败：`MODEL_NETWORK_ERROR`；其他上游失败：`MODEL_UNAVAILABLE`。
- 不明确/不支持的问题：`MODEL_NEEDS_CLARIFICATION`；截断：`MODEL_OUTPUT_TRUNCATED`；非法 JSON、工具、参数或多个调用：`MODEL_INVALID_RESPONSE`。
- 不自动重试，不静默切模型，不把错误转换为 0 个客户或旧价格。
- 日志仅记录模块、动作、traceId、错误码和耗时，不记录 Authorization、问题、模型原文或客户详情。控制台 INFO 输出由应用入口配置；冒烟入口已配置。
- 配置只允许官方 HTTPS 地址且拒绝 HTTP 重定向，避免误配地址或跳转泄露密钥。

## 离线验证

```powershell
python -m unittest discover -s ai-assistant/agent_core/tests -v
python -m unittest discover -s ai-assistant/crm-dashboard/tests -v
```

模型测试使用 mock 和合成记录，不读取真实客户，不产生 API 费用。历史阶段一报告仍只证明其当时内容快照，新增适配使用单独的 AWR 任务和报告。

协议依据：[官方 API 入门](https://api-docs.deepseek.com/quick_start/agent_integrations/)、[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)、[工具调用](https://api-docs.deepseek.com/guides/tool_calls/)。

## Windows 加密保存（本机使用）

先在 DeepSeek 控制台作废此前发在聊天里的旧 Key 并新建 Key；不要再次发到聊天中。首次在 PowerShell 进入 CMR 项目根目录后执行：

```powershell
Set-Location D:\Code\CMR
.\scripts\deepseek-secret.ps1 -Action Save
```

程序会隐藏输入新 Key，使用 Windows DPAPI 当前用户加密后写入 `.secrets/deepseek.dpapi`。该目录被 `.gitignore` 忽略；脚本还会检查目标没有被 Git 跟踪。它拒绝覆盖已有加密文件。不要使用 `git add -f` 强制添加该目录。

每次在用于启动后端或冒烟测试的同一个 PowerShell 窗口中加载：

```powershell
.\scripts\deepseek-secret.ps1 -Action Load
```

加载后 `DEEPSEEK_API_KEY` 只在当前进程和它启动的子进程中可用，不会写入用户级环境变量。变量是进程内明文，结束时可运行 `Remove-Item Env:DEEPSEEK_API_KEY`。DPAPI 默认绑定当前 Windows 用户及本机；换账户、换电脑、云服务器或重装系统通常不能直接解密，需要重新配置云平台密钥管理。加密并不能防止同一账户或已控制电脑的恶意程序读取。请妥善保护 Windows 账户和项目目录。

以上命令只配置密钥，不会调用 DeepSeek 或启动网页；真实 API、身份认证与网页集成仍需另行验证。若要在线测试，请按本文件“显式在线测试”操作，该操作会计费。