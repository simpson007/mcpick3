from __future__ import annotations

import json
from .models import DecisionCard


def render_markdown(cards: list[DecisionCard]) -> str:
    lines = ["# 今天吃啥？· McPick3", "", "> 刚刚查到的门店结果，价格和供应以官方实时数据为准。", ""]
    for card in cards:
        c = card.candidate
        official = c.official_price or {}
        price_line = f"- 到手价：¥{c.total:.2f}（原价 ¥{c.subtotal:.2f}，优惠 ¥{c.discount:.2f}）"
        if official:
            price_line += "｜官方实时校价"
        lines += [
            f"## {card.title}｜{card.subtitle}",
            f"**{' + '.join(c.meal_names)}**",
            price_line,
            f"- 能量：约 {c.kcal:.0f} kcal　蛋白质：约 {c.protein:.1f} g",
            f"- 推荐理由：{'；'.join(c.reasons)}",
            "- 证据：" + "；".join(card.evidence),
            "",
        ]
    return "\n".join(lines)


def render_json(cards: list[DecisionCard]) -> str:
    return json.dumps([card.to_dict() for card in cards], ensure_ascii=False, indent=2)
