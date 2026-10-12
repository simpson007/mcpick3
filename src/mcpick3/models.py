from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal


@dataclass(frozen=True)
class UserConstraints:
    """The three questions plus two optional context fields."""

    budget: float
    kcal_limit: float
    pickup_mode: Literal["pickup", "delivery", "dine_in"] = "pickup"
    minutes: int = 25
    location: str | None = None
    avoid: tuple[str, ...] = ()

    def validate(self) -> None:
        if self.budget <= 0:
            raise ValueError("预算必须大于 0")
        if self.kcal_limit <= 0:
            raise ValueError("热量上限必须大于 0")
        if self.minutes <= 0:
            raise ValueError("可接受等待时间必须大于 0")
        if self.pickup_mode not in {"pickup", "delivery", "dine_in"}:
            raise ValueError("取餐方式必须是 pickup、delivery 或 dine_in")


@dataclass(frozen=True)
class Meal:
    id: str
    name: str
    category: str
    price: float
    kcal: float
    protein: float
    tags: tuple[str, ...] = ()
    prep_minutes: int = 10
    available: bool = True
    product_code: str | None = None
    original_price: float | None = None
    image: str | None = None


@dataclass(frozen=True)
class Coupon:
    id: str
    title: str
    discount: float
    min_spend: float = 0
    meal_ids: tuple[str, ...] = ()

    def applies(self, meal_ids: set[str], subtotal: float) -> bool:
        return subtotal >= self.min_spend and (
            not self.meal_ids or bool(meal_ids.intersection(self.meal_ids))
        )


@dataclass
class Candidate:
    meals: list[Meal]
    subtotal: float
    discount: float
    total: float
    kcal: float
    protein: float
    coupon: Coupon | None
    score: float = 0
    reasons: list[str] = field(default_factory=list)
    official_price: dict[str, Any] | None = None

    @property
    def meal_names(self) -> list[str]:
        return [m.name for m in self.meals]


@dataclass
class DecisionCard:
    mode: str
    title: str
    subtitle: str
    candidate: Candidate
    evidence: list[str]

    def to_dict(self) -> dict[str, Any]:
        c = self.candidate
        return {
            "mode": self.mode,
            "title": self.title,
            "subtitle": self.subtitle,
            "items": c.meal_names,
            "subtotal": round(c.subtotal, 2),
            "discount": round(c.discount, 2),
            "total": round(c.total, 2),
            "kcal": round(c.kcal),
            "protein_g": round(c.protein, 1),
            "coupon": c.coupon.title if c.coupon else None,
            "product_codes": [m.product_code or m.id for m in c.meals],
            "official_price": c.official_price,
            "reasons": c.reasons,
            "evidence": self.evidence,
        }
