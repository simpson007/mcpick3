# McPick3 发布检查清单

## 首屏

- [ ] README 第一屏有一句话定位
- [ ] 有一张三卡结果截图或 GIF
- [ ] 有 60 秒演示链接
- [ ] 明确“实时核价、不自动下单”

## 功能

- [x] 本地演示无需 Token
- [x] 实时 MCP 门店、菜单、营养和核价
- [x] 三种可解释目标
- [x] 套餐默认组成和替换项
- [x] 便宜点 / 低卡点 / 换一个
- [x] 分享结果卡和复制文案
- [x] 选定一张卡并保存到本地浏览器
- [x] 订单草稿，不创建订单

## 安全

- [x] Token 只读环境变量或 `.env.local`
- [x] `.env.local` 被 Git 忽略
- [x] 只监听 `127.0.0.1`
- [x] 不记录地址、手机号、账户券标识
- [x] 不调用支付、下单、自动领券

## 验证命令

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m py_compile src/mcpick3/*.py
python3 - <<'PY'
from pathlib import Path
s = Path('src/mcpick3/index.html').read_text()
a, b = s.index('<script>') + 8, s.index('</script>')
Path('/tmp/mcpick3.js').write_text(s[a:b])
PY
node --check /tmp/mcpick3.js
git diff --check
```
