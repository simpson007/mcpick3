from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .models import Coupon, Meal


class McdMcpError(RuntimeError):
    pass


class McdMcpClient:
    """Small dependency-free Streamable HTTP MCP client.

    It intentionally exposes only the operations used by McPick3. The token is
    read at runtime from MCD_MCP_TOKEN and is never written to disk.
    """

    def __init__(self, url: str = "https://mcp.mcd.cn", token: str | None = None, timeout: int = 20):
        self.url = url.rstrip("/")
        self.token = token or os.getenv("MCD_MCP_TOKEN")
        self.timeout = timeout
        self.session_id: str | None = None
        self._request_id = 0

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if not self.token:
            raise McdMcpError("未检测到 MCD_MCP_TOKEN；请设置环境变量后再连接官方 MCP")
        self._request_id += 1
        payload = {"jsonrpc": "2.0", "id": self._request_id, "method": method}
        if params is not None:
            payload["params"] = params
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(self.url, json.dumps(payload).encode(), headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                sid = response.headers.get("Mcp-Session-Id")
                if sid:
                    self.session_id = sid
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise McdMcpError(f"MCP HTTP {exc.code}: {detail[:300]}") from exc
        except urllib.error.URLError as exc:
            raise McdMcpError(f"MCP 网络请求失败: {exc.reason}") from exc
        result = _parse_mcp_payload(raw)
        if isinstance(result, dict) and result.get("error"):
            raise McdMcpError(str(result["error"]))
        result = result.get("result", result) if isinstance(result, dict) else result
        # MCD returns a typed structuredContent envelope alongside Markdown.
        if isinstance(result, dict) and result.get("structuredContent") is not None:
            return result["structuredContent"]
        return result

    def initialize(self) -> Any:
        return self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "mcpick3", "version": "0.1.0"}})

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        return self._rpc("tools/call", {"name": name, "arguments": arguments or {}})

    def calculate_price(
        self,
        store_id: str,
        items: list[dict[str, Any]],
        coupon_id: str | None = None,
        *,
        be_type: int = 1,
        be_code: str | None = None,
        order_type: int = 1,
        need_tableware: bool = False,
    ) -> Any:
        """Ask the official server for the final, store-specific payable amount."""
        args: dict[str, Any] = {"storeCode": store_id, "items": items, "beType": be_type, "orderType": order_type, "needTableware": need_tableware}
        if be_code:
            args["beCode"] = be_code
        if coupon_id and items:
            items = [dict(items[0], couponId=coupon_id), *items[1:]]
            args["items"] = items
        return self.call_tool("calculate-price", args)

    def create_order(self, store_id: str, items: list[dict[str, Any]], dining_type: str = "pickup", *, confirm: bool = False, be_type: int = 1, be_code: str | None = None, order_type: int = 1, take_way_code: str | None = None) -> Any:
        """Create an order only after the caller has explicitly confirmed it."""
        if not confirm:
            raise ValueError("创建订单前必须传入 confirm=True；McPick3 默认只生成订单草稿")
        args: dict[str, Any] = {"storeCode": store_id, "items": items, "beType": be_type, "orderType": order_type}
        if be_code:
            args["beCode"] = be_code
        if take_way_code:
            args["takeWayCode"] = take_way_code
        return self.call_tool("create-order", args)

    def recommend_context(
        self,
        location: str | None = None,
        *,
        city: str | None = None,
        keyword: str | None = None,
        be_type: int = 1,
    ) -> dict[str, Any]:
        """Fetch the MCP data needed by the decision engine.

        Tool argument schemas can evolve; callers may pass a prebuilt context to
        the engine when the MCP service returns a schema-specific response.
        """
        self.initialize()
        if city or keyword or location:
            city = city or location
            keyword = keyword or location
            store_args: dict[str, Any] = {"searchType": 2, "beType": be_type, "city": city, "keyword": keyword}
        else:
            store_args = {"searchType": 1, "beType": be_type}
        stores = self.call_tool("query-nearby-stores", store_args)
        if isinstance(stores, dict) and stores.get("success") is False:
            raise McdMcpError(f"查询门店失败：{stores.get('message', '未知错误')}")
        store_rows = _data_list(stores)
        if not store_rows:
            raise McdMcpError("没有找到可用门店；请同时提供城市和附近位置关键词")
        first_store = store_rows[0]
        store_id = _first_id(first_store, "storeCode", "storeId", "id")
        if not store_id:
            raise McdMcpError("门店响应缺少 storeCode")
        be_code = first_store.get("beCode") if isinstance(first_store, dict) else None
        order_type = 1 if be_type in (1, 5) else 2
        meal_args: dict[str, Any] = {"storeCode": store_id, "orderType": order_type, "beType": be_type}
        if be_code:
            meal_args["beCode"] = be_code
        meals = self.call_tool("query-meals", meal_args)
        coupons = self.call_tool("query-my-coupons", {"page": "1", "pageSize": "200"})
        coupon_args: dict[str, Any] = {"storeCode": store_id, "orderType": order_type, "beType": be_type}
        if be_code:
            coupon_args["beCode"] = be_code
        store_coupons = self.call_tool("query-store-coupons", coupon_args)
        nutrition = self.call_tool("list-nutrition-foods", {})
        return {"stores": stores, "meals": meals, "coupons": _merge_lists(coupons, store_coupons), "nutrition": nutrition, "store_id": store_id, "be_code": be_code, "order_type": order_type, "be_type": be_type}


def _parse_mcp_payload(raw: str) -> Any:
    raw = raw.strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Streamable HTTP may return one or more SSE data frames.
        frames = []
        for line in raw.splitlines():
            if line.startswith("data:"):
                data = line[5:].strip()
                if data and data != "[DONE]":
                    try:
                        frames.append(json.loads(data))
                    except json.JSONDecodeError:
                        pass
        if not frames:
            raise McdMcpError(f"无法解析 MCP 返回：{raw[:200]}")
        return frames[-1]


def _merge_lists(*values: Any) -> list[Any]:
    """Flatten common MCP tool-result envelopes into a list for adapters."""
    merged: list[Any] = []
    for value in values:
        if isinstance(value, list):
            merged.extend(value)
        elif isinstance(value, dict):
            if isinstance(value.get("data"), dict) and isinstance(value["data"].get("coupons"), list):
                merged.extend(value["data"]["coupons"])
                continue
            content = value.get("content")
            if isinstance(content, list):
                for item in content:
                    text = item.get("text") if isinstance(item, dict) else None
                    if text:
                        try:
                            decoded = json.loads(text)
                            merged.extend(decoded if isinstance(decoded, list) else [decoded])
                        except json.JSONDecodeError:
                            merged.append(item)
                    else:
                        merged.append(item)
            else:
                merged.append(value)
    return merged


def _data_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, dict):
        data = value.get("data")
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            for key in ("stores", "items", "coupons"):
                if isinstance(data.get(key), list):
                    return [x for x in data[key] if isinstance(x, dict)]
    return []


def _first_id(value: Any, *keys: str) -> str | None:
    if isinstance(value, dict):
        for key in keys:
            if value.get(key):
                return str(value[key])
        for child in value.values():
            found = _first_id(child, *keys)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _first_id(child, *keys)
            if found:
                return found
    return None


class DemoMcpClient:
    """Deterministic local fixture for demos and tests; no network or token."""

    def __init__(self) -> None:
        self.meals = [
            Meal("m1", "麦辣鸡腿堡", "主食", 22.0, 520, 22, ("满足感", "经典"), 8),
            Meal("m2", "板烧鸡腿堡", "主食", 24.0, 460, 27, ("均衡", "经典"), 8),
            Meal("m3", "双层吉士汉堡", "主食", 25.0, 600, 32, ("满足感",), 9),
            Meal("m4", "麦香鸡", "主食", 14.0, 400, 16, ("轻食",), 7),
            Meal("s1", "玉米杯", "小食", 8.0, 110, 3, ("轻食", "均衡"), 3),
            Meal("s2", "薯条（中）", "小食", 13.0, 320, 4, ("满足感",), 4),
            Meal("s3", "四季鲜蔬杯", "小食", 9.0, 80, 3, ("轻食", "均衡"), 3),
            Meal("d1", "可口可乐（中）", "饮料", 8.0, 180, 0, ("满足感",), 2),
            Meal("d2", "冰露矿泉水", "饮料", 3.0, 0, 0, ("轻食",), 1),
        ]
        self.coupons = [
            Coupon("c1", "满30减5元", 5, 30),
            Coupon("c2", "满25减3元", 3, 25),
        ]

    def recommend_context(self, location: str | None = None) -> dict[str, Any]:
        return {"stores": [{"id": "demo-store", "name": "示例门店", "eta_minutes": 12}], "meals": self.meals, "coupons": self.coupons, "store_id": "demo-store"}
