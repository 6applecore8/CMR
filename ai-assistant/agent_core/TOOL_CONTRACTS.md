# 只读工具契约 v1：阶段一

这是 Python 领域调用契约，不是已上线的 HTTP API 或模型服务。

## 身份与调用

ToolDispatcher.execute(call, principal, trace_id)。principal 来自未来认证层，trace_id 由服务入口生成。工具参数不能提供用户、组织、角色、SQL 或当前时间。

```json
{"name":"count_customers","arguments":{"tier":"A","channel":"all"}}
```

## 工具参数

| name | 参数 | 结果 |
|---|---|---|
| count_customers | tier 可省略或 A/B/C；channel=all/alibaba/email | 全部授权记录的 count，不受列表分页影响 |
| search_customers | 上述过滤 + keyword + page>=1 + size=1..50 | 白名单摘要、total、分页、requiresSelection |
| get_customer_detail | clientId，必填 | 授权客户的明确字段；缺失的地址与需求为 null |
| get_current_price | productId/specification/currency/unit/tradeTerm/quantity 必填；customerId 可省略 | 当前价格或 REVIEW_REQUIRED；禁止旧金额冒充当前价 |

quantity 是正的十进制字符串，例如 "10.5"，不用浮点数。价格当前仅支持精确维度匹配；缺少规格、单位或币种时应先补充，不推测默认值。

客户搜索的结果是候选而非确认身份。requiresSelection=true 时应让用户按客户 ID 选择；前端与未来模型都不能擅自把第一条当成目标客户。

## 结果格式

以下为合成示例，不代表真实业务数量。

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "kind": "customer_count",
    "state": "OK",
    "count": 1,
    "filters": {"tier":"A","channel":"all"},
    "scope": "owned",
    "source": "customer_repository",
    "asOf": "2026-10-26T10:00:00+00:00"
  },
  "traceId": "synthetic-trace"
}
```

价格不适用时：data.state=REVIEW_REQUIRED、canQuote=false、currentPrice=null，reason 表示具体拒用原因。历史入口受 allow_history 控制；草稿和未来报价不作为历史可用提示。

当前价格的 amount 为十进制字符串，同时返回 priceId、revision、sourceRef、适用维度、数量档位和有效期。validUntilExclusive 和 maxQuantityExclusive 都是排他上界。

## 错误映射

| code | 建议 HTTP 状态 | 行为 |
|---|---|---|
| INVALID_PRINCIPAL | 401 | 重新认证 |
| FORBIDDEN | 403 | 显示权限不足，不自动改角色 |
| CUSTOMER_NOT_FOUND | 404 | 不存在与无访问权使用同一结果 |
| INVALID_ARGUMENT / UNKNOWN_TOOL | 400 | 修正参数，不无限重试 |
| POLICY_VERSION_CONFLICT | 409 | 重新读取政策并确认变更 |
| SOURCE_INCONSISTENT | 503 | 交管理层检查，不能显示正常零条 |
| MODEL_NOT_CONFIGURED | 503 | 明确说明未接入模型，不生成假回答 |
| MODEL_CONFIG_INVALID / MODEL_AUTH_FAILED / MODEL_BALANCE_INSUFFICIENT | 503 | 后端修正配置或余额，不回显密钥 |
| MODEL_RATE_LIMITED | 503 | 显示限流，不自动重复计费调用 |
| MODEL_TIMEOUT / MODEL_NETWORK_ERROR | 504 | 明确调用失败，不返回虚假统计 |
| MODEL_INVALID_RESPONSE / MODEL_OUTPUT_TRUNCATED / MODEL_UNAVAILABLE | 502 | 拒绝异常上游输出，不执行工具 |
| MODEL_NEEDS_CLARIFICATION | 422 | 请求补充条件，不采用模型自由文本作业务事实 |

OSError 等未知仓储异常必须由未来全局处理层记录安全错误码并返回 5xx；不得把异常原文、客户原文或堆栈放进响应。

## 管理政策

change_policy 仅生成新 PricingPolicy 快照，要求 manager、同组织和 expected_version 匹配；不执行数据库保存，不声称已经有审批审计。

变更后的持久化、审计、缓存失效与并发写入保护在阶段二完成。旧 CRM 接口仍未鉴权，不能直接承载这些身份假设或公开给外部客户。
