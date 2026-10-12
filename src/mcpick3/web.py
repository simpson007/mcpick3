from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .decision_engine import DecisionEngine
from .mcp_client import DemoMcpClient
from .models import UserConstraints


HTML = """<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>麦麦三问 · McPick3</title>
<style>
body{margin:0;background:#fff8ef;color:#2d211b;font:16px system-ui,-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:42px 20px}.hero{display:flex;justify-content:space-between;gap:20px;align-items:end;margin-bottom:28px}
h1{font-size:42px;line-height:1.1;margin:0}.tag{color:#da291c;font-weight:700}.sub{color:#6e5e55;margin-top:12px}
form{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;background:#fff;padding:18px;border-radius:18px;box-shadow:0 8px 30px #5d311411}
label{font-size:13px;color:#6e5e55}input,select,button{width:100%;box-sizing:border-box;padding:12px;border:1px solid #ead8ca;border-radius:10px;background:white;font:inherit}button{background:#da291c;color:white;border:0;font-weight:700;cursor:pointer;margin-top:19px}
#cards{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:22px}.card{background:#fff;border-radius:18px;padding:20px;box-shadow:0 8px 30px #5d311411;border-top:5px solid #da291c}.card:nth-child(2){border-color:#f0a400}.card:nth-child(3){border-color:#2f855a}
.mode{font-size:13px;color:#6e5e55}.price{font-size:30px;font-weight:800;margin:8px 0}.items{font-size:19px;font-weight:700;min-height:52px}.stats{display:flex;gap:14px;font-size:13px;color:#6e5e55}.reason{margin-top:14px;font-size:14px;line-height:1.7}.evidence{font-size:11px;line-height:1.6;color:#8a7770;margin-top:16px;border-top:1px solid #f2e6dd;padding-top:10px}
.hint{margin-top:18px;color:#8a7770;font-size:13px}@media(max-width:760px){form,#cards{grid-template-columns:1fr 1fr}.hero{display:block}h1{font-size:34px}}@media(max-width:480px){form,#cards{grid-template-columns:1fr}}
</style>
<div class="wrap"><div class="hero"><div><div class="tag">McPick3 · 麦麦三问</div><h1>三问，给你今天最合适的一餐。</h1><div class="sub">输入预算、热量和取餐时间，得到三张可解释决策卡。</div></div></div>
<form id="form"><div><label>预算（元）</label><input name="budget" type="number" min="1" value="35"></div><div><label>热量上限（kcal）</label><input name="kcal" type="number" min="1" value="700"></div><div><label>可接受时间（分钟）</label><input name="minutes" type="number" min="1" value="25"></div><div><label>取餐方式</label><select name="mode"><option value="pickup">到店取餐</option><option value="delivery">外送</option><option value="dine_in">堂食</option></select></div><button>生成我的三张卡</button></form>
<div id="cards"></div><div class="hint">演示模式使用本地样本数据；接入官方 MCP 后，价格、库存与优惠以实时结果为准。</div></div>
<script>
const f=document.querySelector('#form'),out=document.querySelector('#cards');
function esc(s){return String(s).replace(/[&<>\"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[x]))}
f.onsubmit=async e=>{e.preventDefault();const q=new URLSearchParams(new FormData(f));const r=await fetch('/api/cards?'+q);const cards=await r.json();out.innerHTML=cards.map(c=>`<article class="card"><div class="mode">${esc(c.title)} · ${esc(c.subtitle)}</div><div class="price">¥${c.total.toFixed(2)}</div><div class="items">${c.items.map(esc).join(' + ')}</div><div class="stats"><span>${c.kcal} kcal</span><span>${c.protein_g} g 蛋白质</span></div><div class="reason">${c.reasons.map(esc).join('<br>')}</div><div class="evidence">${c.evidence.map(esc).join('<br>')}</div></article>`).join('')};f.dispatchEvent(new Event('submit'));
</script>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/cards":
            query = parse_qs(parsed.query)
            try:
                constraints = UserConstraints(float(query.get("budget", [35])[0]), float(query.get("kcal", [700])[0]), query.get("mode", ["pickup"])[0], int(query.get("minutes", [25])[0]))
                cards = DecisionEngine.from_context(DemoMcpClient().recommend_context()).generate(constraints)
                payload = json.dumps([card.to_dict() for card in cards], ensure_ascii=False).encode()
                self.send_response(200)
            except (ValueError, TypeError) as exc:
                payload = json.dumps({"error": str(exc)}, ensure_ascii=False).encode()
                self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
        else:
            payload = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args) -> None:
        pass


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("McPick3 demo: http://127.0.0.1:8765")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
