import json
import unittest
from pathlib import Path

from verdict_lab.adapters.deepseek import DeepSeekFlashAdapter
from verdict_lab.adapters.jev import OpenRouterJevAdapter
from verdict_lab.models import ModerationCase
from verdict_lab.taxonomy import load_taxonomy, validate_scores


class PayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, cls.directions = load_taxonomy("config/taxonomy.json")
        cls.case = ModerationCase("case-1", "加我站外账号", "test", "test")

    def test_jev_uses_independent_noul_questions(self):
        payload = OpenRouterJevAdapter.build_payload(self.case, self.directions, "typesafe/jev-1.13")
        self.assertTrue(all(question["type"] == "noul" for question in payload["questions"].values()))
        self.assertEqual(payload["state"]["records"][0]["record"], self.case.content)

    def test_deepseek_prompt_says_not_to_normalize(self):
        payload = DeepSeekFlashAdapter.build_payload(self.case, self.directions, "deepseek-flash")
        self.assertIn("禁止让所有分数之和归一化为1", payload["messages"][0]["content"])
        self.assertEqual(payload["thinking"], {"type": "disabled"})

    def test_scores_do_not_need_to_sum_to_one(self):
        scores = {item.id: 0.8 for item in self.directions}
        clean, errors = validate_scores(scores, self.directions)
        self.assertFalse(errors)
        self.assertGreater(sum(clean.values()), 1)

    def test_english_case_uses_english_instructions(self):
        case = ModerationCase("en", "User prompt:\ntext", "aegis", "test", metadata={"language": "en"})
        payload = DeepSeekFlashAdapter.build_payload(case, self.directions, "deepseek-flash")
        self.assertIn("content-safety classifier", payload["messages"][0]["content"])
        jev = OpenRouterJevAdapter.build_payload(case, self.directions, "typesafe/jev-1.13")
        self.assertIn("English user-assistant conversation", jev["state"]["description"])


if __name__ == "__main__":
    unittest.main()
