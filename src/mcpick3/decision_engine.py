from __future__ import annotations

from itertools import combinations
from copy import deepcopy
from typing import Iterable, Any, Callable

from .models import Candidate, Coupon, DecisionCard, Meal, UserConstraints


class DecisionEngine:
    """Turn live (or demo) MCP data into three distinct, explainable cards."""

    def __init__(self, meals: Iterable[Meal], coupons: Iterable[Coupon] = ()):
        self.meals = [m for m in meals if m.available]
        self.coupons = list(coupons)

    @classmethod
    def from_context(cls, context: dict[str, Any]) -> "DecisionEngine":
        meals = _extract_mcd_meals(context.get("meals"), context.get("nutrition"))
        # Official coupons include eligibility/product rules that differ from
        # the demo's fixed discount model. Do not invent discounts for live data.
        coupons = [] if context.get("live") else [_coupon_from_any(x) for x in _as_list(context.get("coupons")) if _is_coupon(x)]
        return cls(meals, coupons)

    def generate(self, constraints: UserConstraints, limit: int = 3, *, verifier: Callable[[Candidate], Candidate] | None = None,
                 excluded_keys: set[tuple[str, ...]] | None = None) -> list[DecisionCard]:
        constraints.validate()
        excluded_keys = excluded_keys or set()
        candidates = self._candidates(constraints)
        if not candidates:
            raise ValueError("没有同时满足预算和热量上限的可售组合，请放宽一个条件")
        modes = [
            ("save", "省钱党", "能省就省，别委屈自己"),
            ("balance", "稳妥一餐", "价格、能量都不冒险"),
            ("mood", "今天就吃它", "想吃的那口，直接安排"),
        ]
        cards: list[DecisionCard] = []
        used: set[tuple[str, ...]] = set()
        failures: set[tuple[str, ...]] = set()
        verified: dict[tuple[str, ...], Candidate] = {}
        for mode, title, subtitle in modes[:limit]:
            ordered = sorted(candidates, key=lambda c: self._score(c, constraints, mode), reverse=True)
            pick = None
            attempts = 0
            for candidate in ordered:
                key = tuple(m.id for m in candidate.meals)
                if key in used or key in failures or key in excluded_keys:
                    continue
                if verifier and key not in verified:
                    attempts += 1
                    if attempts > 5:
                        break
                    try:
                        verified[key] = verifier(deepcopy(candidate))
                    except ValueError:
                        failures.add(key)
                        continue
                result = verified.get(key, candidate)
                if result.total > constraints.budget:
                    failures.add(key)
                    continue
                pick = deepcopy(result)
                break
            if pick is None:
                continue
            used.add(tuple(m.id for m in pick.meals))
            pick.score = self._score(pick, constraints, mode)
            pick.reasons = self._reasons(pick, constraints, mode)
            cards.append(DecisionCard(mode, title, subtitle, pick, self._evidence(pick, constraints)))
        if not cards:
            raise ValueError("当前条件下没有通过实时校价的组合，请调整预算或门店后重试")
        return cards

    def apply_official_prices(self, cards: list[DecisionCard], price_results: list[Any]) -> list[DecisionCard]:
        """Overlay calculate-price responses while retaining local ranking."""
        for card, result in zip(cards, price_results):
            data = result.get("data", result) if isinstance(result, dict) else result
            if isinstance(data, dict) and result.get("success", True) is not False:
                total = _number(data, "price")
                if total is None or total < 0:
                    raise ValueError("校价响应缺少有效的 price（单位分）")
                card.candidate.total = total / 100
                card.candidate.subtotal = (_number(data, "originalPrice") or total) / 100
                card.candidate.discount = (_number(data, "discount") or 0) / 100
                card.candidate.official_price = data
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
                    if len({m.category for m in extra_tuple}) != len(extra_tuple):
                        continue
                    if any(any(term.lower() in m.name.lower() for term in c.avoid) for m in selected):
                        continue
                    subtotal = sum(m.price for m in selected)
                    kcal = sum(m.kcal for m in selected)
                    if kcal > c.kcal_limit:
                        continue
                    coupon = self._best_coupon(selected, subtotal)
                    discount = coupon.discount if coupon else 0
                    total = max(0, subtotal - discount)
                    if total > c.budget:
                        continue
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
        reasons = [f"¥{candidate.total:.2f}，还剩 ¥{c.budget - candidate.total:.2f}", f"约 {candidate.kcal:.0f} kcal，在你的范围内"]
        if candidate.coupon:
            reasons.append(f"用了「{candidate.coupon.title}」，省 ¥{candidate.discount:.2f}")
        if mode == "balance":
            reasons.append(f"蛋白质约 {candidate.protein:.1f} g，整体比较稳")
        elif mode == "mood":
            reasons.append("想吃的口味，今天就别换了")
        else:
            reasons.append("先把价格压下来")
        return reasons

    @staticmethod
    def _evidence(candidate: Candidate, c: UserConstraints) -> list[str]:
        if candidate.official_price is None:
            return ["本地演示数据：菜单、营养与优惠均为样本", "本地估价：未调用官方 calculate-price"]
        return ["query-meals：读取当前门店菜单", "list-nutrition-foods：按名称精确匹配营养数据",
                "query-meal-detail：核验餐品默认组成", "query-store-coupons：查询门店可用券（未自动领券）",
                "calculate-price：官方实时校价，金额从分换算为元"]


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
                n = nutrition_map.get(name)
                if not n:
                    # A meal without nutrition data must not masquerade as 0 kcal.
                    continue
                result.append(Meal(
                    id=str(code), name=name,
                    category=_category(name),
                    price=float(item.get("currentPrice") or item.get("price") or 0),
                    kcal=float(n.get("kcal", 0)), protein=float(n.get("protein", 0)),
                    product_code=str(code),
                    original_price=float(item.get("originalPrice") or item.get("currentPrice") or 0),
                    image=item.get("image"),
                    tags=tuple(item.get("tags") or ()) + (("满足感",) if any(x in name for x in ("辣", "双层", "巨无霸", "厚牛")) else ()),
                ))
            return result
    return [_meal_from_any(x) for x in _as_list(value)]


def _category(label: str) -> str:
    if any(x in label for x in ("堡", "麦满分", "卷")):
        return "主食"
    if any(x in label for x in ("小食", "薯", "鸡翅", "玉米", "冰淇淋", "麦旋风", "派", "麦乐鸡", "油条", "新地", "鸡排")):
        return "小食"
    if any(x in label for x in ("饮料", "咖啡", "可乐", "饮品", "奶", "茶", "雪碧", "美式", "拿铁", "水")):
        return "饮料"
    if any(x in label for x in ("苹果", "蔬", "沙拉")):
        return "小食"
    return "其他"


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
        product_code=str(value.get("product_code") or value.get("productCode") or value.get("id") or "") or None,
        original_price=float(value.get("original_price") or value.get("originalPrice") or value.get("price") or 0),
        image=value.get("image"),
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


def _is_coupon(value: Any) -> bool:
    return isinstance(value, Coupon) or (
        isinstance(value, dict)
        and bool(value.get("id") or value.get("couponId") or value.get("code"))
        and bool(value.get("title") or value.get("name") or value.get("discountInfo"))
    )


def _number(value: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if value.get(key) is not None:
            try:
                return float(value[key])
            except (TypeError, ValueError):
                pass
    return None
