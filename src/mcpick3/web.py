from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs, urlparse

from .config import get_mcp_token
from .mcp_client import McdMcpClient, McdMcpError
from .models import UserConstraints
from .service import recommendations


class Handler(BaseHTTPRequestHandler):
    def _local_request(self) -> bool:
        host = self.headers.get("Host", "")
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        origin = self.headers.get("Origin")
        return host in allowed and (not origin or origin in {f"http://{h}" for h in allowed})

    def _send(self, value, status=200, content_type="application/json; charset=utf-8"):
        payload = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if not self._local_request():
            self._send({"error": "仅接受本机同源请求"}, 403)
            return
        path = urlparse(self.path).path
        if path == "/":
            self._send(files("mcpick3").joinpath("index.html").read_bytes(), content_type="text/html; charset=utf-8")
        elif path == "/api/status":
            self._send({"token_configured": bool(get_mcp_token()), "order_creation_enabled": False})
        elif path == "/api/cards":
            # Backward-compatible demo-only GET endpoint; live requests require POST.
            query = parse_qs(urlparse(self.path).query)
            try:
                c = UserConstraints(float(query.get("budget", [35])[0]), float(query.get("kcal", [700])[0]),
                                    query.get("mode", ["pickup"])[0], int(query.get("minutes", [25])[0]))
                self._send(recommendations(c)["cards"])
            except (ValueError, TypeError) as exc:
                self._send({"error": str(exc)}, 400)
        else:
            self._send({"error": "路径不存在"}, 404)

    def do_POST(self):
        if not self._local_request():
            self._send({"error": "仅接受本机同源请求"}, 403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8192:
                raise ValueError("请求长度应为 1–8192 字节")
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ValueError("请使用 application/json")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("请求正文应为 JSON 对象")
            city, keyword = str(data.get("city", ""))[:100], str(data.get("keyword", ""))[:100]
            path = urlparse(self.path).path
            if path == "/api/stores":
                client = McdMcpClient()
                client.initialize()
                self._send({"stores": client.search_stores(city, keyword)})
            elif path == "/api/recommend":
                source = data.get("source", "demo")
                if source not in {"demo", "live"}:
                    raise ValueError("source 应为 demo 或 live")
                constraints = UserConstraints(float(data.get("budget", 35)), float(data.get("kcal", 700)),
                                              str(data.get("mode", "pickup")), int(data.get("minutes", 25)))
                if source == "live" and (not city.strip() or not keyword.strip()):
                    raise ValueError("实时模式请同时输入城市和位置关键词")
                result = recommendations(constraints, live=source == "live", city=city, keyword=keyword,
                                         store_code=str(data["storeCode"]) if data.get("storeCode") else None,
                                         exclude=data.get("exclude") if isinstance(data.get("exclude"), list) else None,
                                         replacement=data.get("replacement") if isinstance(data.get("replacement"), dict) else None)
                self._send(result)
            else:
                self._send({"error": "路径不存在；当前网页仅提供查询和草稿"}, 404)
        except (ValueError, TypeError) as exc:
            self._send({"error": str(exc)}, 400)
        except (McdMcpError, OSError) as exc:
            self._send({"error": str(exc)}, 502)

    def log_message(self, *_args):
        pass


def main():
    parser = argparse.ArgumentParser(description="McPick3 本地网页")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"McPick3: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
