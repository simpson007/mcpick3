from __future__ import annotations

import json
import time
import socket
import urllib.error
import urllib.request
from typing import Any

from .models import Coupon, Meal
from .config import get_mcp_token


class McdMcpError(RuntimeError):
    pass


class McdMcpClient:
    """Small dependency-free Streamable HTTP MCP client.

    It intentionally exposes only the operations used by McPick3. The token is
    read at runtime from MCD_MCP_TOKEN or a user-created ignored .env.local.
    """

    def __init__(self, url: str = "https://mcp.mcd.cn", token: str | None = None, timeout: int = 20):
        self.url = url.rstrip("/")
        self.token = token or get_mcp_token()
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
        retries = 3 if _retryable_request(method, params) else 0
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    sid = response.headers.get("Mcp-Session-Id")
                    if sid:
                        self.session_id = sid
                    raw = response.read().decode("utf-8")
                    break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                if exc.code in {429, 502, 503, 504} and attempt < retries:
                    wait = min(2 ** attempt, 4)
                    retry_after = exc.headers.get("Retry-After")
                    try:
                        wait = min(float(retry_after), 4) if retry_after else wait
                    except ValueError:
                        pass
                    time.sleep(wait)
                    continue
                raise McdMcpError(f"MCP HTTP {exc.code}: {detail[:300]}") from exc
            except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
                if attempt < retries:
                    time.sleep(min(2 ** attempt, 4))
                    continue
                raise McdMcpError(f"MCP 网络请求失败: {getattr(exc, 'reason', '请求超时')}") from exc
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
        result = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        if isinstance(result, dict) and (result.get("isError") is True or result.get("success") is False):
            raise McdMcpError(f"{name}：{result.get('message') or '官方工具返回错误'}")
        return result

    def search_stores(self, city: str, keyword: str, *, be_type: int = 1) -> list[dict[str, Any]]:
        if be_type not in (1, 5):
            raise ValueError("当前版本支持到店取餐和得来速；外送与团餐需要单独的配送地址流程")
        if not city.strip() or not keyword.strip():
            raise ValueError("请同时输入城市和附近位置关键词")
        stores = self.call_tool("query-nearby-stores", {
            "searchType": 2, "beType": be_type, "city": city.strip(), "keyword": keyword.strip(),
        })
        rows = _data_list(stores)
        if not rows:
            raise ValueError("没有找到门店，请更换城市或关键词")
        return rows

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

    def meal_detail(self, store_code: str, product_code: str, *, be_type: int = 1, order_type: int = 1, be_code: str | None = None) -> Any:
        args: dict[str, Any] = {"storeCode": store_code, "orderType": order_type, "beType": be_type, "code": product_code}
        if be_code:
            args["beCode"] = be_code
        return self.call_tool("query-meal-detail", args)

    def price_for_candidate(self, context: dict[str, Any], candidate: Any) -> Any:
        """Calculate official price for a Candidate without creating an order."""
        items = [{"productCode": m.product_code or m.id, "quantity": 1} for m in candidate.meals]
        return self.calculate_price(
            context["store_id"], items, be_type=context.get("be_type", 1),
            be_code=context.get("be_code"), order_type=context.get("order_type", 1),
        )

    def verify_candidate(self, context: dict[str, Any], candidate: Any) -> Any:
        """Verify all selected products with official detail and price tools."""
        details = []
        for meal in candidate.meals:
            details.append(self.meal_detail(
                context["store_id"], meal.product_code or meal.id,
                be_type=context.get("be_type", 1), order_type=context.get("order_type", 1),
                be_code=context.get("be_code"),
            ))
        price = self.price_for_candidate(context, candidate)
        return {"details": details, "price": price}

    def verify_candidate_model(self, context: dict[str, Any], candidate: Any) -> Any:
        """Adapter used by DecisionEngine.generate(verifier=...)."""
        result = self.verify_candidate(context, candidate)
        details = result["details"]
        for detail in details:
            if isinstance(detail, dict) and detail.get("success") is False:
                raise ValueError(detail.get("message", "餐品详情校验失败"))
        price = result["price"]
        if isinstance(price, dict) and price.get("success") is False:
            raise ValueError(price.get("message", "价格校验失败"))
        payload = price.get("data", {}) if isinstance(price, dict) else {}
        if not isinstance(payload, dict) or payload.get("price") is None:
            raise ValueError("价格响应缺少 price")
        candidate.details = details
        # Keep the official product structure in the draft. The selected
        # default choices are visible to the user and can be rechecked before
        # any future order flow; no order is created here.
        candidate.order_items = [_default_order_item(meal, detail)
                                 for meal, detail in zip(candidate.meals, details)]
        candidate.official_price = payload
        candidate.total = float(payload["price"]) / 100
        candidate.subtotal = float(payload.get("originalPrice", payload["price"])) / 100
        candidate.discount = float(payload.get("discount", 0)) / 100
        return candidate

    def recommend_context(
        self,
        location: str | None = None,
        *,
        city: str | None = None,
        keyword: str | None = None,
        be_type: int = 1,
        store_code: str | None = None,
    ) -> dict[str, Any]:
        """Fetch the MCP data needed by the decision engine.

        Tool argument schemas can evolve; callers may pass a prebuilt context to
        the engine when the MCP service returns a schema-specific response.
        """
        if be_type not in (1, 5):
            raise ValueError("当前版本支持到店取餐和得来速；外送与团餐需要单独的配送地址流程")
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
        if store_code:
            first_store = next((s for s in store_rows if s.get("storeCode") == store_code), None)
            if first_store is None:
                raise ValueError("所选门店不在当前搜索结果中，请重新选择")
        else:
            first_store = next((s for s in store_rows if s.get("businessStatus") is True), store_rows[0])
        if first_store.get("businessStatus") is False:
            raise ValueError("所选门店当前暂停营业，请选择其他门店")
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
        return {"stores": stores, "selected_store": first_store, "meals": meals, "coupons": _merge_lists(store_coupons), "my_coupons": coupons, "nutrition": nutrition, "store_id": store_id, "be_code": be_code, "order_type": order_type, "be_type": be_type, "live": True}


def _retryable_request(method: str, params: dict[str, Any] | None) -> bool:
    """Retry read-only MCP calls, never order creation/cancellation."""
    if method in {"initialize", "tools/list", "ping"}:
        return True
    if method != "tools/call":
        return False
    tool = (params or {}).get("name", "")
    return tool in {"query-nearby-stores", "query-meals", "query-meal-detail", "calculate-price", "query-my-coupons", "query-store-coupons", "list-nutrition-foods"}


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


def _has_detail_rounds(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    data = value.get("data") if isinstance(value.get("data"), dict) else value
    return bool(data.get("rounds") or data.get("roundList") or data.get("roundsList"))


def _default_order_item(meal: Any, detail: Any) -> dict[str, Any]:
    item = {"productCode": meal.product_code or meal.id, "quantity": 1}
    data = detail.get("data", detail) if isinstance(detail, dict) else {}
    if not isinstance(data, dict):
        return item
    rounds = data.get("rounds") or data.get("roundList") or data.get("roundsList") or []
    selections = []
    for round_ in rounds if isinstance(rounds, list) else []:
        choices = round_.get("choices") or round_.get("choiceList") or round_.get("items") or []
        for choice in choices if isinstance(choices, list) else []:
            if isinstance(choice, dict) and choice.get("isDefault") in (1, True, "1", "true"):
                selections.append({"roundCode": round_.get("code") or round_.get("roundCode"),
                                   "productCode": choice.get("code") or choice.get("productCode"),
                                   "quantity": 1})
                break
    if selections:
        item["roundItems"] = selections
    return item


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
