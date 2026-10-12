from __future__ import annotations

import argparse
import json
from .decision_engine import DecisionEngine
from .mcp_client import DemoMcpClient, McdMcpClient
from .models import UserConstraints
from .render import render_json, render_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description="麦麦三问 McPick3")
    parser.add_argument("--budget", type=float, required=True, help="预算，例如 35")
    parser.add_argument("--kcal", type=float, required=True, help="热量上限，例如 700")
    parser.add_argument("--minutes", type=int, default=25)
    parser.add_argument("--mode", choices=["pickup", "delivery", "dine_in"], default="pickup")
    parser.add_argument("--location")
    parser.add_argument("--city", help="实时 MCP 门店搜索城市")
    parser.add_argument("--keyword", help="实时 MCP 门店搜索关键词")
    parser.add_argument("--be-type", type=int, choices=[1, 2, 5, 6], default=1, help="1到店取餐，2麦乐送，5得来速，6团餐")
    parser.add_argument("--live", action="store_true", help="调用官方 MCP；默认使用本地演示数据")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args()
    client = McdMcpClient() if args.live else DemoMcpClient()
    if args.live:
        context = client.recommend_context(args.location, city=args.city, keyword=args.keyword, be_type=args.be_type)
    else:
        context = client.recommend_context(args.location)
    if args.live:
        engine = DecisionEngine.from_context(context)
        cards = engine.generate(UserConstraints(args.budget, args.kcal, args.mode, args.minutes, args.location))
        for card in cards:
            try:
                result = client.price_for_candidate(context, card.candidate)
                engine.apply_official_prices([card], [result])
            except Exception as exc:
                card.evidence.append(f"calculate-price：实时校价失败（{exc}），保留菜单价")
    else:
        cards = DecisionEngine.from_context(context).generate(UserConstraints(args.budget, args.kcal, args.mode, args.minutes, args.location))
    print(render_json(cards) if args.format == "json" else render_markdown(cards))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
