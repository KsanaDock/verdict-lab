import json
import tempfile
import unittest
from pathlib import Path

from verdict_lab.datasets import load_aegis, load_chinese_harm, load_cold


class DatasetTests(unittest.TestCase):
    def test_chinese_harm_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bench.json"
            path.write_text(json.dumps([{"文本": "测试", "标签": "黑产广告"}], ensure_ascii=False), encoding="utf-8")
            case = next(iter(load_chinese_harm(path)))
            self.assertTrue(case.gold["illicit_advertising"])
            self.assertFalse(case.gold["gambling"])
            self.assertNotIn("advertising", case.gold)

    def test_cold_fine_label(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.csv"
            path.write_text(",split,topic,label,fine-grained-label,TEXT\n7,test,race,1,2,测试\n", encoding="utf-8")
            case = next(iter(load_cold(path)))
            self.assertEqual(case.gold, {"abuse_harassment": True})
            self.assertEqual(case.case_id, "cold:test:7")

    def test_aegis_conversation_mapping_and_redacted_skip(self):
        rows = [
            {
                "id": "visible",
                "reconstruction_id_if_redacted": None,
                "prompt": "user text",
                "response": "assistant text",
                "prompt_label": "unsafe",
                "response_label": "safe",
                "violated_categories": "Violence, Threat",
                "prompt_label_source": "human",
                "response_label_source": "human",
            },
            {
                "id": "hidden",
                "reconstruction_id_if_redacted": 42,
                "prompt": "REDACTED",
                "response": None,
                "prompt_label": "unsafe",
                "response_label": None,
                "violated_categories": "Suicide and Self Harm",
                "prompt_label_source": "human",
                "response_label_source": None,
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.json"
            path.write_text(json.dumps(rows), encoding="utf-8")
            cases = list(load_aegis(path))
            self.assertEqual(len(cases), 1)
            case = cases[0]
            self.assertTrue(case.gold["unsafe_overall"])
            self.assertTrue(case.gold["violence"])
            self.assertTrue(case.gold["threat"])
            self.assertFalse(case.gold["fraud_deception"])
            self.assertIn("Assistant response", case.content)
            self.assertEqual(case.metadata["language"], "en")


if __name__ == "__main__":
    unittest.main()
