import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from verdict_lab.cli import _saved_cases
from verdict_lab.models import ModerationCase


class SavedCaseTests(unittest.TestCase):
    def test_literal_unicode_line_separator_stays_inside_jsonl_record(self):
        case = ModerationCase("case-1", "before\u2028after", "fixture", "test")
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "cases.jsonl").write_text(
                json.dumps(asdict(case), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            loaded = _saved_cases(run_dir)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].content, "before\u2028after")


if __name__ == "__main__":
    unittest.main()
