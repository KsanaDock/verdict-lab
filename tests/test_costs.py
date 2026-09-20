import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from verdict_lab.costs import deepseek_cost
from verdict_lab.models import Usage


class DeepSeekCostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pricing = json.loads(Path("config/pricing.json").read_text(encoding="utf-8"))

    def test_off_peak_cache_cost(self):
        usage = Usage(completion_tokens=100, prompt_cache_hit_tokens=900, prompt_cache_miss_tokens=100)
        cost, source = deepseek_cost(usage, datetime(2026, 9, 20, 2, tzinfo=timezone.utc), self.pricing)
        self.assertAlmostEqual(cost, (900 * 0.003 + 100 * 0.15 + 100 * 0.6) / 1_000_000)
        self.assertTrue(source.endswith("off_peak"))

    def test_peak_cost(self):
        usage = Usage(completion_tokens=100, prompt_cache_hit_tokens=900, prompt_cache_miss_tokens=100)
        cost, source = deepseek_cost(usage, datetime(2026, 9, 21, 2, tzinfo=timezone.utc), self.pricing)
        self.assertAlmostEqual(cost, (900 * 0.006 + 100 * 0.3 + 100 * 1.2) / 1_000_000)
        self.assertTrue(source.endswith("peak"))


if __name__ == "__main__":
    unittest.main()

