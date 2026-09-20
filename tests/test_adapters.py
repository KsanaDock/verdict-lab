import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

from verdict_lab.adapters.deepseek import DeepSeekFlashAdapter
from verdict_lab.adapters.jev import OpenRouterJevAdapter
from verdict_lab.models import ModerationCase
from verdict_lab.taxonomy import load_taxonomy


class AdapterResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pricing = json.loads(Path("config/pricing.json").read_text(encoding="utf-8"))
        _, _, cls.directions = load_taxonomy("config/taxonomy.json")
        cls.case = ModerationCase("x", "测试文本", "fixture", "test")

    def test_deepseek_usage_and_scores(self):
        scores = {item.id: 0.75 for item in self.directions}

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": json.dumps({"scores": scores})}}],
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 20,
                        "total_tokens": 120,
                        "prompt_cache_hit_tokens": 80,
                        "prompt_cache_miss_tokens": 20,
                    },
                },
            )

        adapter = DeepSeekFlashAdapter("test", self.pricing)
        adapter.client.close()
        adapter.client = httpx.Client(transport=httpx.MockTransport(handler))
        result = adapter.evaluate(self.case, self.directions, 0.5)
        adapter.close()
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.probability_source, "self_reported")
        self.assertEqual(result.usage.prompt_cache_hit_tokens, 80)
        self.assertIsNotNone(result.cost_usd)

    def test_jev_native_probabilities_and_reported_cost(self):
        answers = {item.id: {"noul": 0.6} for item in self.directions}

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"answers": answers, "usage": {"cost": 0.00012}})

        adapter = OpenRouterJevAdapter("test", self.pricing)
        adapter.client.close()
        adapter.client = httpx.Client(transport=httpx.MockTransport(handler))
        result = adapter.evaluate(self.case, self.directions, 0.5)
        adapter.close()
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.probability_source, "native_distribution")
        self.assertEqual(result.cost_usd, 0.00012)
        self.assertEqual(result.cost_source, "provider_reported")


if __name__ == "__main__":
    unittest.main()
