"""Shared read-only recommendation workflow for CLI and local web UI."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .decision_engine import DecisionEngine
from .mcp_client import DemoMcpClient, McdMcpClient
from .models import ReplacementRequest, UserConstraints


def recommendations(constraints: UserConstraints, *, live: bool = False, city: str = "",
                    keyword: str = "", store_code: str | None = None, be_type: int = 1,
                    client: McdMcpClient | None = None,
                    exclude: list[list[str]] | None = None,
                    replacement: dict[str, Any] | None = None) -> dict[str, Any]:
    constraints.validate()
    if constraints.pickup_mode == "delivery":
        raise ValueError("外送功能尚未接入，请选择到店取餐或堂食")
    warnings = ["时间只用来帮你筛选，实际出餐以门店现场为准。"]
    if live:
        client = client or McdMcpClient()
        context = client.recommend_context(city=city, keyword=keyword, store_code=store_code, be_type=be_type)
        engine = DecisionEngine.from_context(context)
        excluded_keys = {tuple(str(x) for x in group) for group in (exclude or [])}
        replacement_request = ReplacementRequest(**replacement) if replacement else None
        cards = engine.generate(constraints, verifier=lambda c: client.verify_candidate_model(context, c),
                                excluded_keys=excluded_keys, replacement=replacement_request)
        store = context["selected_store"]
        warnings.append("这次只挑了营养信息完整、刚刚校过价的单品；套餐和优惠券组合还没算进去。")
    else:
        context = DemoMcpClient().recommend_context()
        engine = DecisionEngine.from_context(context)
        excluded_keys = {tuple(str(x) for x in group) for group in (exclude or [])}
        replacement_request = ReplacementRequest(**replacement) if replacement else None
        cards = engine.generate(constraints, excluded_keys=excluded_keys, replacement=replacement_request)
        store = {"storeCode": "demo-store", "storeName": "演示门店", "address": "本地样本，不代表真实供应"}
        warnings.append("现在是演示数据；切到实时 MCP 才会查真实门店和价格。")
    serialized = []
    for card in cards:
        value = card.to_dict()
        value["details"] = [_detail_summary(d.get("data", d)) for d in card.candidate.details]
        items = card.candidate.order_items or [{"productCode": m.id, "quantity": 1} for m in card.candidate.meals]
        value["draft"] = {
            "status": "draft_only", "note": "仅订单草稿，尚未创建订单或付款；下单前应再次校价并确认取餐方式。",
            "storeCode": store["storeCode"], "orderType": 1, "beType": be_type,
            "items": items, "amount_yuan": round(card.candidate.total, 2),
            "takeWayOptions": (card.candidate.official_price or {}).get("takeWayList", []),
        }
        if context.get("be_code"):
            value["draft"]["beCode"] = context["be_code"]
        serialized.append(value)
    return {
        "source": "live" if live else "demo", "store": store,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cards": serialized, "warnings": warnings,
        "coverage": {"recommended_meals": len(engine.meals), "cards": len(serialized)},
    }


def _detail_summary(data: dict[str, Any]) -> dict[str, Any]:
    """Show default composition and modify flag, not unsolicited modification lists."""
    data = _unwrap_detail(data)
    defaults = []
    options = []
    for round_ in _detail_rounds(data):
        round_name = round_.get("name") or round_.get("roundName") or round_.get("title") or "可选项"
        choices = round_.get("choices") or round_.get("choiceList") or round_.get("items") or []
        if not isinstance(choices, list):
            continue
        round_options = []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            item = {"name": choice.get("name", ""), "code": choice.get("code") or choice.get("productCode", ""),
                    "supportModify": bool(choice.get("supportModify")),
                    "default": choice.get("isDefault") in (1, True, "1", "true")}
            round_options.append(item)
            if item["default"]:
                defaults.append(item)
        if round_options:
            options.append({"name": round_name, "choices": round_options})
    return {"code": data.get("code"), "name": data.get("name"),
            "supportModify": bool(data.get("supportModify")), "defaults": defaults, "options": options}


def _unwrap_detail(value: Any) -> dict[str, Any]:
    """Accept both structuredContent and common MCP data envelopes."""
    if not isinstance(value, dict):
        return {}
    current = value
    for _ in range(3):
        nested = current.get("data")
        if isinstance(nested, dict) and (not current.get("rounds") and not current.get("roundList")):
            current = nested
        else:
            break
    return current


def _detail_rounds(data: dict[str, Any]) -> list[dict[str, Any]]:
    rounds = data.get("rounds") or data.get("roundList") or data.get("roundsList") or []
    if isinstance(rounds, dict):
        rounds = rounds.get("items") or rounds.get("list") or []
    return [item for item in rounds if isinstance(item, dict)] if isinstance(rounds, list) else []
