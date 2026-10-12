# MCP 集成说明

## Server 与传输

- Server：`https://mcp.mcd.cn`
- 协议：Streamable HTTP
- 鉴权：`Authorization: Bearer ${MCD_MCP_TOKEN}`
- 限流：每个 Token 每分钟最多 600 次请求

配置见 [`mcp-config.example.json`](mcp-config.example.json)。示例只包含环境变量占位符。

## McPick3 使用的 Tool

| Tool | 用途 |
|---|---|
| `query-nearby-stores` | 按位置找到可用门店与取餐上下文 |
| `query-meals` | 读取当前门店可售餐品 |
| `query-meal-detail` | 补充套餐组成和可替换项（可选增强） |
| `list-nutrition-foods` | 读取能量、蛋白质等营养信息 |
| `query-my-coupons` | 读取用户账户可用券 |
| `query-store-coupons` | 读取当前门店可用券 |
| `calculate-price` | 按门店实时规则计算优惠后应付金额 |
| `create-order` | 用户确认订单草稿后创建订单（可选执行） |
| `order-list` | 读取近期订单，用于偏好记忆（可选增强） |

## 调用流程

```text
用户三问
  ↓
query-nearby-stores
  ↓
query-meals ──→ query-meal-detail
  ↓
list-nutrition-foods
  ↓
query-my-coupons + query-store-coupons
  ↓
本地决策引擎：硬约束过滤 + 三目标排序
  ↓
calculate-price（对候选卡做最终价格确认）
  ↓
输出三张卡 → 用户确认 → create-order
```

## 连接自检

网页实时模式的「先做连接自检」只执行只读调用：`initialize` 和
`query-nearby-stores`。它会告诉你 Token 是否被读取、MCP 是否可连通以及找到多少家门店，
不会调用下单、支付、领券或地址接口，也不会把 Token 写进页面或日志。

命令行中也可以使用同一逻辑：

```python
from mcpick3.mcp_client import McdMcpClient

print(McdMcpClient().diagnostics("YOUR_CITY", "YOUR_NEARBY_KEYWORD"))
```

可能的结果：

```text
{'ok': True, 'stage': 'query-nearby-stores', 'message': '官方 MCP 连接正常', ...}
```

凭证缺失、网络错误和上游错误只返回脱敏诊断，不回显 Token。

MVP 的 `McdMcpClient` 负责连接和工具调用；因官方工具参数可能按版本更新，`recommend_context` 将原始返回交给适配层，避免把某一时刻的字段写死。`DemoMcpClient` 提供无 Token 的本地演示与测试数据。

## 业务价值

- 把“翻菜单、找券、算热量、算价格”压缩成三问。
- 用可解释证据行降低推荐黑箱感。
- 多目标输出让用户在省钱、均衡和满足感之间快速选择。
- 通过订单草稿和二次确认连接到真实执行，而不是停留在内容生成。

## 安全边界

Token 只从环境变量读取；仓库不保存真实凭证。项目默认不自动下单、不自动支付，只有用户明确确认后才调用 `create-order`。营养与价格信息以麦当劳官方实时结果为准。
