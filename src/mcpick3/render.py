from __future__ import annotations

import json
from .models import DecisionCard


def render_markdown(cards: list[DecisionCard]) -> str:
    lines = ["# 麦麦三问 · 今日决策卡", "", "> 营养信息、价格与供应状态以麦当劳官方实时结果为准。", ""]
    for card in cards:
        c = card.candidate
        lines += [
            f"## {card.title}｜{card.subtitle}",
            f"**{' + '.join(c.meal_names)}**",
            f"- 到手价：¥{c.total:.2f}（原价 ¥{c.subtotal:.2f}，优惠 ¥{c.discount:.2f}）",
            f"- 能量：约 {c.kcal:.0f} kcal　蛋白质：约 {c.protein:.1f} g",
            f"- 推荐理由：{'；'.join(c.reasons)}",
            "- 证据：" + "；".join(card.evidence),
            "",
        ]
    return "\n".join(lines)


def render_json(cards: list[DecisionCard]) -> str:
    return json.dumps([card.to_dict() for card in cards], ensure_ascii=False, indent=2)
