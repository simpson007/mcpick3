# 麦麦三问 McPick3

> 三问，给你今天最合适的一餐。

McPick3 是一个基于麦当劳 MCP 的可解释点餐决策 Skill。用户只需输入 **预算、热量上限、取餐方式/时间**，它会把菜单、营养、优惠券和价格计算串成一条短链路，输出「省钱优先 / 均衡优先 / 心情优先」三张实时决策卡，并在用户确认后生成订单。

**项目状态：** 可运行 MVP。默认使用本地演示数据；设置 `MCD_MCP_TOKEN` 并加 `--live` 后连接麦当劳官方 MCP。项目为参赛作品，非麦当劳官方产品，输出仅供参考。

## 60 秒体验

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
mcpick3 --budget 35 --kcal 700 --minutes 25
```

预期输出三张卡：

```text
省钱优先｜到手价 ¥22.00｜约 480 kcal｜优先降低实际支付金额
均衡优先｜到手价 ¥29.00｜约 570 kcal｜价格、能量与蛋白质的折中解
心情优先｜到手价 ¥30.00｜约 700 kcal｜保留更有满足感的口味组合
```

输出 JSON 便于前端或 WorkBuddy 消费：

```bash
mcpick3 --budget 35 --kcal 700 --format json
```

## 目标用户

- 工作日只有 20–30 分钟午休的上班族
- 想同时考虑预算和营养信息的麦当劳用户
- 希望少翻菜单、少算价格、直接得到可执行选择的人

## 真实 MCP 模式

1. 在 [麦当劳 MCP](https://open.mcd.cn/mcp) 申请 Token。
2. 设置环境变量（不要把 Token 写进仓库）：

```bash
export MCD_MCP_TOKEN='YOUR_MCP_TOKEN'
```

3. 连接官方 Streamable HTTP Server：

```bash
mcpick3 --live --budget 35 --kcal 700 --minutes 25 --location 'YOUR_LOCATION'
```

MVP 会读取附近门店、当前菜单、营养和优惠数据；生成订单前应在客户端展示草稿并让用户再次确认。完整调用说明见 [MCP_INTEGRATION.md](MCP_INTEGRATION.md)。

## 为什么是三张卡

McPick3 不做“又一个菜单查询器”：它在多重现实约束下做一次可解释决策。每张卡都给出总价、优惠额、能量、蛋白质、推荐理由和证据行，用户知道**为什么推荐**，而不是只看到一个黑箱答案。

## 开发

```bash
pip install -e '.[dev]'  # 若本地有测试依赖
python -m unittest discover -s tests
```

目录：

```text
src/mcpick3/
├── decision_engine.py  # 约束过滤、三目标排序、解释生成
├── mcp_client.py       # 官方 MCP Streamable HTTP + 本地 Demo fixture
├── models.py           # 输入、餐品、优惠券、决策卡数据模型
├── render.py           # Markdown/JSON 输出
└── cli.py              # 命令行入口
```

## 合规与隐私

- `MCD_MCP_TOKEN` 只从环境变量读取；仓库不保存真实 Token。
- 不写入手机号、地址等个人信息。
- 创建订单前必须用户确认。
- 营养信息仅作点餐参考，不构成医疗、营养或其他专业建议。
- 官方实时结果可能因门店、时间和库存变化，请以官方渠道为准。

## 相关资料

- [活动说明](https://github.com/M-China/mcd-developer-innovation-challenge/blob/main/README.md)
- [活动规则](https://github.com/M-China/mcd-developer-innovation-challenge/blob/main/activityGuidelines.md)
- [麦当劳 MCP 工具清单](https://github.com/M-China/mcd-mcp-server/blob/main/README.md)
