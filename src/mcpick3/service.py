"""Shared read-only recommendation workflow for CLI and local web UI."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .decision_engine import DecisionEngine
from .mcp_client import DemoMcpClient, McdMcpClient
from .models import UserConstraints


def recommendations(constraints: UserConstraints, *, live: bool = False, city: str = "",
                    keyword: str = "", store_code: str | None = None, be_type: int = 1,
                    client: McdMcpClient | None = None) -> dict[str, Any]:
    constraints.validate()
    if constraints.pickup_mode == "delivery":
        raise ValueError("外送功能尚未接入，请选择到店取餐或堂食")
    warnings = ["取餐时间为用户偏好：官方接口没有提供实时出餐 ETA，本版本不承诺指定分钟内完成。"]
    if live:
        client = client or McdMcpClient()
        context = client.recommend_context(city=city, keyword=keyword, store_code=store_code, be_type=be_type)
        engine = DecisionEngine.from_context(context)
        cards = engine.generate(constraints, verifier=lambda c: client.verify_candidate_model(context, c))
        store = context["selected_store"]
        warnings.append("仅推荐营养信息完整且通过详情与价格校验的单品组合；套餐、未知营养和优惠券自动搭配尚未启用。")
    else:
        context = DemoMcpClient().recommend_context()
        engine = DecisionEngine.from_context(context)
        cards = engine.generate(constraints)
        store = {"storeCode": "demo-store", "storeName": "演示门店", "address": "本地样本，不代表真实供应"}
        warnings.append("演示模式使用虚构价格、营养与优惠，不是官方查询结果。")
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
    defaults = []
    for round_ in data.get("rounds", []):
        for choice in round_.get("choices", []):
            if choice.get("isDefault") == 1:
                defaults.append({"name": choice.get("name", ""), "code": choice.get("code", ""),
                                 "supportModify": bool(choice.get("supportModify"))})
    return {"code": data.get("code"), "name": data.get("name"),
            "supportModify": bool(data.get("supportModify")), "defaults": defaults}
