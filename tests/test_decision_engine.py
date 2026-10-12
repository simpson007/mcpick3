import unittest

from mcpick3.decision_engine import DecisionEngine
from mcpick3.mcp_client import DemoMcpClient
from mcpick3.models import UserConstraints


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
