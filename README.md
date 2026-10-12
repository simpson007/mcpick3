# 麦麦三问 McPick3

> 三问，给你今天最合适的一餐。

McPick3 是一个基于麦当劳 MCP 的可解释点餐决策 Skill。用户只需输入 **预算、热量上限、取餐方式/时间**，它会把菜单、营养、优惠券和价格计算串成一条短链路，输出「省钱优先 / 均衡优先 / 心情优先」三张实时决策卡，并在用户确认后生成订单。

**项目状态：** 可发布的本地 Web MVP（v0.3.0）。默认使用本地演示数据；设置 `MCD_MCP_TOKEN` 后可连接麦当劳官方 MCP。项目为参赛作品，非麦当劳官方产品，输出仅供参考。

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

启动一个零依赖的本地演示页面（适合录制参赛 Demo）：

```bash
mcpick3-web
# 浏览器打开 http://127.0.0.1:8765
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

独立终端的 `export` 不会同步给 Codex 的命令进程。若需跨进程调试，可在已设置
Token 的终端中保存到项目目录下的 `.env.local`（已被 Git 忽略）：

```bash
cd /Users/yushenjian/Downloads/mchina
if [ -n "$MCD_MCP_TOKEN" ]; then
  (umask 077; printf 'MCD_MCP_TOKEN=%s\n' "$MCD_MCP_TOKEN" > .env.local)
  chmod 600 .env.local
  echo '本地凭证已保存'
else
  echo '请先在此终端设置 MCD_MCP_TOKEN'
fi
```

环境变量优先于本地文件。请勿分享或提交 `.env.local`。

3. 连接官方 Streamable HTTP Server：

```bash
mcpick3 --live --budget 35 --kcal 700 --minutes 25 --location 'YOUR_LOCATION'
```

MVP 会读取附近门店、当前菜单、营养和优惠数据；生成订单前应在客户端展示草稿并让用户再次确认。完整调用说明见 [MCP_INTEGRATION.md](MCP_INTEGRATION.md)。

## 为什么是三张卡

McPick3 不做“又一个菜单查询器”：它在多重现实约束下做一次可解释决策。每张卡都给出总价、优惠额、能量、蛋白质、推荐理由和证据行，用户知道**为什么推荐**，而不是只看到一个黑箱答案。

## 适合分享的一句话

每张卡都可以复制成不含 Token、门店地址和账户信息的轻量分享文案：

```text
今天我是：省钱党｜麦辣鸡腿堡 + 中薯条｜¥24.00｜约 560 kcal
月底也能吃得明白
```

分享的是“怎么点”和“为什么”，不是个人凭证；真实价格和供应仍以当前门店为准。

## 发布前检查

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m py_compile src/mcpick3/*.py
python3 -m mcpick3.web --port 8765
```

网页默认只监听 `127.0.0.1`，Token 只从环境变量或被 Git 忽略的 `.env.local` 读取。实时模式只查询门店、菜单、营养、套餐详情和价格；订单接口保留在客户端中但默认关闭。

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

- Token 从环境变量或已忽略的 `.env.local` 读取；Git 仓库不保存真实 Token。
- 不写入手机号、地址等个人信息。
- 创建订单前必须用户确认。
- 营养信息仅作点餐参考，不构成医疗、营养或其他专业建议。
- 官方实时结果可能因门店、时间和库存变化，请以官方渠道为准。

## 相关资料

- [活动说明](https://github.com/M-China/mcd-developer-innovation-challenge/blob/main/README.md)
- [活动规则](https://github.com/M-China/mcd-developer-innovation-challenge/blob/main/activityGuidelines.md)
- [麦当劳 MCP 工具清单](https://github.com/M-China/mcd-mcp-server/blob/main/README.md)
