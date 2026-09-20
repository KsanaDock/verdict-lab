import unittest
import contextlib
import io
import json
import tempfile
from pathlib import Path
from unittest import mock

import httpx

from verdict_lab.adapters.base import ModerationAdapter
from verdict_lab.models import ModelResult, ModerationCase, Usage
from verdict_lab.runner import _atomic_json, _build_summary, _read_attempts, run_comparison


def successful_result(case_id: str, provider: str = "fake") -> ModelResult:
    return ModelResult(
        case_id, provider, "fake-model", "ok", {"fraud": 0.9}, "self_reported",
        ["fraud"], 1, Usage(prompt_tokens=1, completion_tokens=1), 0.01, "test", {},
    )


class InterruptingAdapter(ModerationAdapter):
    model = "fake-model"

    def __init__(self):
        self.calls = 0

    def evaluate(self, case, directions, threshold):
        self.calls += 1
        if self.calls == 2:
            raise KeyboardInterrupt()
        return successful_result(case.case_id)


class SuccessAdapter(ModerationAdapter):
    model = "fake-model"

    def __init__(self):
        self.calls = 0

    def evaluate(self, case, directions, threshold):
        self.calls += 1
        return successful_result(case.case_id)


class QuotaAdapter(ModerationAdapter):
    model = "fake-model"

    def __init__(self):
        self.calls = 0

    def evaluate(self, case, directions, threshold):
        self.calls += 1
        request = httpx.Request("POST", "https://example.test")
        response = httpx.Response(402, request=request, json={"error": "insufficient balance"})
        raise httpx.HTTPStatusError("payment required", request=request, response=response)


class RunnerSummaryTests(unittest.TestCase):
    def test_atomic_json_falls_back_when_replace_is_locked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.json"
            path.write_text('{"old": true}', encoding="utf-8")
            with mock.patch.object(Path, "replace", side_effect=PermissionError("locked")):
                saved = _atomic_json(path, {"new": True}, retries=1, retry_delay=0)
            self.assertTrue(saved)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"new": True})
            self.assertFalse((Path(directory) / "summary.json.tmp").exists())

    def test_quality_uses_only_labeled_directions(self):
        cases = {
            "a": ModerationCase("a", "", "fixture", "test", gold={"fraud": True}),
            "b": ModerationCase("b", "", "fixture", "test", gold={"fraud": False}),
        }
        results = [
            ModelResult("a", "p", "m", "ok", {"fraud": 0.9, "violence": 0.9}, "self_reported", ["fraud", "violence"], 10, Usage(), 0.1, "test", {}),
            ModelResult("b", "p", "m", "ok", {"fraud": 0.2, "violence": 0.9}, "self_reported", ["violence"], 20, Usage(), 0.2, "test", {}),
        ]
        summary = _build_summary(results, cases, 0.5)["p"]
        fraud = summary["quality_by_labeled_direction"]["fraud"]
        self.assertEqual(fraud["accuracy"], 1.0)
        self.assertNotIn("violence", summary["quality_by_labeled_direction"])
        self.assertAlmostEqual(summary["total_cost_usd"], 0.3)

    def test_resume_skips_completed_case(self):
        cases = [
            ModerationCase(
                str(index),
                "x\u2028y" if index == 1 else "x",
                "fixture",
                "test",
                gold={"fraud": True},
            )
            for index in range(3)
        ]
        with tempfile.TemporaryDirectory() as directory:
            first = InterruptingAdapter()
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                with self.assertRaises(KeyboardInterrupt):
                    run_comparison(cases, {"fake": first}, [], 0.5, directory)
            run_dir = next(Path(directory).iterdir())
            self.assertIn("[VerdictLab][INTERRUPTED]", output.getvalue())
            self.assertIn("event=run_interrupted", (run_dir / "errors.log").read_text(encoding="utf-8"))
            partial = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))["fake"]
            self.assertEqual(partial["completed_cases"], 1)
            second = SuccessAdapter()
            with contextlib.redirect_stdout(io.StringIO()):
                run_comparison(cases, {"fake": second}, [], 0.5, resume_dir=run_dir)
            self.assertEqual(second.calls, 2)
            final = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))["fake"]
            self.assertEqual(final["completed_cases"], 3)
            self.assertEqual(final["attempts"], 3)
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "complete")

    def test_quota_error_pauses_provider_after_one_attempt(self):
        cases = [ModerationCase(str(index), "x", "fixture", "test") for index in range(3)]
        with tempfile.TemporaryDirectory() as directory:
            adapter = QuotaAdapter()
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                run_dir = run_comparison(cases, {"fake": adapter}, [], 0.5, directory)
            self.assertEqual(adapter.calls, 1)
            self.assertIn("[VerdictLab][PAUSED]", output.getvalue())
            error_log = (run_dir / "errors.log").read_text(encoding="utf-8")
            self.assertIn("pause_reason=billing_or_quota", error_log)
            self.assertIn("status=provider_error", error_log)
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "paused")
            self.assertEqual(manifest["paused_providers"], ["fake"])

    def test_legacy_openrouter_result_maps_to_jev_adapter(self):
        result = successful_result("a", provider="openrouter")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.jsonl"
            path.write_text(json.dumps(result.to_dict(include_raw=False)) + "\n", encoding="utf-8")
            _, latest, _ = _read_attempts(path)
            self.assertIn(("a", "jev"), latest)


if __name__ == "__main__":
    unittest.main()
