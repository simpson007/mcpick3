import unittest

from mcpick3.decision_engine import DecisionEngine
from mcpick3.mcp_client import DemoMcpClient
from mcpick3.models import ReplacementRequest, UserConstraints
from mcpick3.service import _detail_summary


class DecisionEngineTest(unittest.TestCase):
    def test_generates_three_distinct_cards_with_constraints(self):
        context = DemoMcpClient().recommend_context()
        cards = DecisionEngine.from_context(context).generate(UserConstraints(35, 700, minutes=25))
        self.assertEqual(len(cards), 3)
        self.assertEqual(len({tuple(c.candidate.meal_names) for c in cards}), 3)
        for card in cards:
            self.assertLessEqual(card.candidate.total, 35)
            self.assertLessEqual(card.candidate.kcal, 700)


    def test_invalid_constraints(self):
        with self.assertRaisesRegex(ValueError, "预算"):
            DecisionEngine([]).generate(UserConstraints(0, 700))

    def test_excluded_combination_is_not_returned(self):
        context = DemoMcpClient().recommend_context()
        engine = DecisionEngine.from_context(context)
        first = engine.generate(UserConstraints(35, 700), limit=1)[0]
        excluded = tuple(m.id for m in first.candidate.meals)
        second = engine.generate(UserConstraints(35, 700), limit=1,
                                 excluded_keys={excluded})[0]
        self.assertNotEqual(tuple(m.id for m in second.candidate.meals), excluded)

    def test_cheaper_replacement_stays_below_reference_price(self):
        context = DemoMcpClient().recommend_context()
        engine = DecisionEngine.from_context(context)
        first = engine.generate(UserConstraints(35, 700), limit=1)[0]
        request = ReplacementRequest("save", "cheaper", reference_total=first.candidate.total,
                                     reference_kcal=first.candidate.kcal)
        replacement = engine.generate(UserConstraints(35, 700), limit=1,
                                      excluded_keys={engine._key(first.candidate)},
                                      replacement=request)[0]
        self.assertLess(replacement.candidate.total, first.candidate.total)

    def test_detail_summary_supports_round_list_and_defaults(self):
        summary = _detail_summary({"data": {"name": "示例套餐", "roundList": [
            {"roundName": "饮料", "choiceList": [
                {"name": "冰露", "code": "d2", "isDefault": 1},
                {"name": "可乐", "code": "d1", "isDefault": 0},
            ]}
        ]}})
        self.assertEqual(summary["name"], "示例套餐")
        self.assertEqual(summary["defaults"][0]["code"], "d2")
        self.assertEqual(summary["options"][0]["choices"][1]["name"], "可乐")
