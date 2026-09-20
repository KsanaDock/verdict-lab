from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MODEL_NAMES = {
    "jev": "Jev 1.13",
    "deepseek": "DeepSeek Flash",
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_results(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").split("\n"):
        if not line.strip():
            continue
        record = json.loads(line)
        adapter = record.get("adapter_id") or record["provider"]
        latest[(record["case_id"], adapter)] = record
    return latest


def export_run(run_dir: Path) -> dict[str, Any]:
    manifest = _read_json(run_dir / "manifest.json")
    summary = _read_json(run_dir / "summary.json")
    taxonomy = _read_json(run_dir / "taxonomy.snapshot.json")
    latest = _latest_results(run_dir / "results.jsonl")
    providers = list(manifest["providers"])
    case_ids = {case_id for case_id, _ in latest}
    paired = sum(
        all(latest.get((case_id, provider), {}).get("status") == "ok" for provider in providers)
        for case_id in case_ids
    )
    direction_names = {item["id"]: item["name"] for item in taxonomy["directions"]}

    models: list[dict[str, Any]] = []
    for provider in providers:
        item = summary[provider]
        total_cost = item["total_cost_usd"]
        models.append(
            {
                "id": provider,
                "name": MODEL_NAMES.get(provider, provider),
                "model": manifest["metadata"]["model_configs"][provider]["model"],
                "completed": item["completed_cases"],
                "remaining": item["remaining_cases"],
                "attempts": item["attempts"],
                "failedAttempts": item["failed_attempts"],
                "costUsd": total_cost if total_cost is not None else item["known_cost_subtotal_usd"],
                "costIsLowerBound": total_cost is None,
                "costPerThousandUsd": (
                    (total_cost if total_cost is not None else item["known_cost_subtotal_usd"])
                    / item["completed_cases"]
                    * 1000
                ),
                "promptTokens": item["prompt_tokens"],
                "completionTokens": item["completion_tokens"],
                "cacheHitTokens": item["prompt_cache_hit_tokens"],
                "cacheMissTokens": item["prompt_cache_miss_tokens"],
                "latency": item["latency_ms"],
                "overall": item["quality_by_labeled_direction"].get("unsafe_overall"),
            }
        )

    direction_ids = list(summary[providers[0]]["quality_by_labeled_direction"])
    directions = []
    for direction_id in direction_ids:
        metrics = {
            provider: summary[provider]["quality_by_labeled_direction"].get(direction_id)
            for provider in providers
        }
        support = max(
            ((metric or {}).get("tp", 0) + (metric or {}).get("fn", 0))
            for metric in metrics.values()
        )
        directions.append(
            {
                "id": direction_id,
                "name": direction_names.get(direction_id, direction_id),
                "support": support,
                "metrics": metrics,
            }
        )

    return {
        "runId": manifest["run_id"],
        "dataset": manifest["metadata"]["dataset"],
        "datasetName": "Aegis AI Content Safety 2.0"
        if manifest["metadata"]["dataset"] == "aegis"
        else manifest["metadata"]["dataset"],
        "split": "test",
        "status": manifest["status"],
        "updatedAt": manifest["updated_at"],
        "caseCount": manifest["case_count"],
        "pairedCompleted": paired,
        "pairedCoverage": paired / manifest["case_count"],
        "threshold": manifest["threshold"],
        "taxonomyVersion": manifest["metadata"]["taxonomy_version"],
        "models": models,
        "directions": directions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export aggregate, public-safe benchmark data")
    parser.add_argument("--run", action="append", required=True, type=Path)
    parser.add_argument("--output", default=Path("site/data/benchmarks.json"), type=Path)
    args = parser.parse_args()
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "privacy": "Aggregate metrics only; no prompts, responses, API keys, or case identifiers.",
        "benchmarks": [export_run(path) for path in args.run],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {len(payload['benchmarks'])} benchmark(s) to {args.output}")


if __name__ == "__main__":
    main()
