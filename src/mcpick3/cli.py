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
    parser.add_argument("--live", action="store_true", help="调用官方 MCP；默认使用本地演示数据")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args()
    client = McdMcpClient() if args.live else DemoMcpClient()
    context = client.recommend_context(args.location)
    cards = DecisionEngine.from_context(context).generate(UserConstraints(args.budget, args.kcal, args.mode, args.minutes, args.location))
    print(render_json(cards) if args.format == "json" else render_markdown(cards))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
