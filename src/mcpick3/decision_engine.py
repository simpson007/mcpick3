from __future__ import annotations

from itertools import combinations
from typing import Iterable, Any

from .models import Candidate, Coupon, DecisionCard, Meal, UserConstraints


class DecisionEngine:
    """Turn live (or demo) MCP data into three distinct, explainable cards."""

    def __init__(self, meals: Iterable[Meal], coupons: Iterable[Coupon] = ()):
        self.meals = [m for m in meals if m.available]
        self.coupons = list(coupons)

    @classmethod
    def from_context(cls, context: dict[str, Any]) -> "DecisionEngine":
        meals = _extract_mcd_meals(context.get("meals"), context.get("nutrition"))
        coupons = [_coupon_from_any(x) for x in _as_list(context.get("coupons"))]
        return cls(meals, coupons)

    def generate(self, constraints: UserConstraints, limit: int = 3) -> list[DecisionCard]:
        constraints.validate()
        candidates = self._candidates(constraints)
        if not candidates:
            raise ValueError("没有同时满足预算和热量上限的可售组合，请放宽一个条件")
        modes = [
            ("save", "省钱优先", "把优惠用在刀刃上"),
            ("balance", "均衡优先", "价格、能量与蛋白质的折中解"),
            ("mood", "心情优先", "更有满足感的一餐"),
        ]
        cards: list[DecisionCard] = []
        used: set[tuple[str, ...]] = set()
        for mode, title, subtitle in modes[:limit]:
            ordered = sorted(candidates, key=lambda c: self._score(c, constraints, mode), reverse=True)
            pick = next((c for c in ordered if tuple(m.id for m in c.meals) not in used), ordered[0])
            used.add(tuple(m.id for m in pick.meals))
            pick.score = self._score(pick, constraints, mode)
            pick.reasons = self._reasons(pick, constraints, mode)
            cards.append(DecisionCard(mode, title, subtitle, pick, self._evidence(pick, constraints)))
        return cards

    def _candidates(self, c: UserConstraints) -> list[Candidate]:
        # Keep combinations small and human-readable: one main + up to two sides/drinks.
        mains = [m for m in self.meals if m.category in {"主食", "套餐"}]
        extras = [m for m in self.meals if m.category not in {"主食", "套餐"}]
        result: list[Candidate] = []
        for main in mains:
            for size in range(0, min(2, len(extras)) + 1):
                for extra_tuple in combinations(extras, size):
                    selected = [main, *extra_tuple]
                    if any(any(term.lower() in m.name.lower() for term in c.avoid) for m in selected):
                        continue
                    subtotal = sum(m.price for m in selected)
                    kcal = sum(m.kcal for m in selected)
                    if subtotal > c.budget or kcal > c.kcal_limit:
                        continue
                    coupon = self._best_coupon(selected, subtotal)
                    discount = coupon.discount if coupon else 0
                    total = max(0, subtotal - discount)
                    result.append(Candidate(selected, subtotal, discount, total, kcal, sum(m.protein for m in selected), coupon))
        # De-duplicate exact combinations and retain those with strongest discount.
        unique: dict[tuple[str, ...], Candidate] = {}
        for candidate in result:
            key = tuple(m.id for m in candidate.meals)
            if key not in unique or candidate.total < unique[key].total:
                unique[key] = candidate
        return list(unique.values())

    def _best_coupon(self, meals: list[Meal], subtotal: float) -> Coupon | None:
        ids = {m.id for m in meals}
        applicable = [coupon for coupon in self.coupons if coupon.applies(ids, subtotal)]
        return max(applicable, key=lambda x: x.discount, default=None)

    @staticmethod
    def _score(candidate: Candidate, c: UserConstraints, mode: str) -> float:
        remaining = max(0, c.budget - candidate.total)
        kcal_fit = 1 - abs(c.kcal_limit - candidate.kcal) / max(c.kcal_limit, 1)
        protein = min(candidate.protein / 35, 1)
        discount = candidate.discount / max(c.budget, 1)
        satisfaction = sum(1 for m in candidate.meals if "满足感" in m.tags) / len(candidate.meals)
        if mode == "save":
            return discount * 0.55 + remaining / c.budget * 0.35 + kcal_fit * 0.10
        if mode == "balance":
            return protein * 0.30 + kcal_fit * 0.30 + (1 - remaining / c.budget) * 0.20 + discount * 0.20
        return satisfaction * 0.45 + kcal_fit * 0.20 + discount * 0.15 + protein * 0.20

    @staticmethod
    def _reasons(candidate: Candidate, c: UserConstraints, mode: str) -> list[str]:
        reasons = [f"总价 ¥{candidate.total:.2f}，预算还剩 ¥{c.budget - candidate.total:.2f}", f"约 {candidate.kcal:.0f} kcal，低于 {c.kcal_limit:.0f} kcal 上限"]
        if candidate.coupon:
            reasons.append(f"已匹配「{candidate.coupon.title}」，优惠 ¥{candidate.discount:.2f}")
        if mode == "balance":
            reasons.append(f"蛋白质约 {candidate.protein:.1f} g，适合想吃得更均衡时")
        elif mode == "mood":
            reasons.append("保留更有满足感的口味组合")
        else:
            reasons.append("优先降低实际支付金额")
        return reasons

    @staticmethod
    def _evidence(candidate: Candidate, c: UserConstraints) -> list[str]:
        return [
            "query-meals：确认餐品当前可售",
            "list-nutrition-foods：读取能量与蛋白质信息",
            "query-my-coupons / query-store-coupons：匹配可用优惠",
            "calculate-price：按门店实时规则计算应付金额",
        ]


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("items", "data", "meals", "coupons", "content"):
            if isinstance(value.get(key), list):
                return value[key]
    return []


def _extract_mcd_meals(value: Any, nutrition: Any = None) -> list[Meal]:
    """Adapt the official query-meals map and nutrition text to our model."""
    if isinstance(value, dict):
        data = value.get("data") if isinstance(value.get("data"), dict) else value
        meal_map = data.get("meals") if isinstance(data, dict) else None
        if isinstance(meal_map, dict):
            category_by_code: dict[str, str] = {}
            for category in data.get("categories", []) if isinstance(data, dict) else []:
                if isinstance(category, dict):
                    for item in category.get("meals", []):
                        if isinstance(item, dict) and item.get("code"):
                            category_by_code[str(item["code"])] = str(category.get("name") or "主食")
            nutrition_map = _parse_nutrition(nutrition)
            result = []
            for code, item in meal_map.items():
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or code)
                n = nutrition_map.get(name, {})
                result.append(Meal(
                    id=str(code), name=name,
                    category=_category(category_by_code.get(str(code), "主食")),
                    price=float(item.get("currentPrice") or item.get("price") or 0),
                    kcal=float(n.get("kcal", 0)), protein=float(n.get("protein", 0)),
                    tags=tuple(item.get("tags") or ()),
                ))
            return result
    return [_meal_from_any(x) for x in _as_list(value)]


def _category(label: str) -> str:
    if any(x in label for x in ("小食", "薯", "鸡翅", "玉米")):
        return "小食"
    if any(x in label for x in ("饮料", "咖啡", "可乐", "饮品")):
        return "饮料"
    return "主食"


def _parse_nutrition(value: Any) -> dict[str, dict[str, float]]:
    if not isinstance(value, dict):
        return {}
    data = value.get("data")
    if not isinstance(data, str):
        return {}
    output: dict[str, dict[str, float]] = {}
    for line in data.splitlines():
        line = line.strip()
        if not line or line.startswith("[") or line.startswith("productName"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        try:
            output[parts[0]] = {"kcal": float(parts[3]), "protein": float(parts[4])}
        except (ValueError, IndexError):
            continue
    return output


def _meal_from_any(value: Any) -> Meal:
    if isinstance(value, Meal):
        return value
    return Meal(
        id=str(value.get("id") or value.get("mealId") or value.get("sku") or "unknown"),
        name=str(value.get("name") or value.get("mealName") or "未命名餐品"),
        category=str(value.get("category") or "主食"),
        price=float(value.get("price") or value.get("salePrice") or 0),
        kcal=float(value.get("kcal") or value.get("energy") or value.get("calories") or 0),
        protein=float(value.get("protein") or value.get("protein_g") or 0),
        tags=tuple(value.get("tags") or ()),
        prep_minutes=int(value.get("prep_minutes") or value.get("prepMinutes") or 10),
        available=bool(value.get("available", True)),
    )


def _coupon_from_any(value: Any) -> Coupon:
    if isinstance(value, Coupon):
        return value
    return Coupon(
        id=str(value.get("id") or value.get("couponId") or "coupon"),
        title=str(value.get("title") or value.get("name") or "优惠券"),
        discount=float(value.get("discount") or value.get("discountAmount") or 0),
        min_spend=float(value.get("min_spend") or value.get("minSpend") or 0),
        meal_ids=tuple(value.get("meal_ids") or value.get("mealIds") or ()),
    )
