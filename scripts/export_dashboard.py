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

DATASET_NAMES = {
    "aegis": "Aegis AI Content Safety 2.0",
    "chineseharm": "ChineseHarm-Bench",
    "cold": "COLDataset",
}

PRIMARY_DIRECTIONS = {
    "aegis": ("unsafe_overall", "Overall unsafe"),
    "cold": ("abuse_harassment", "Abuse / harassment"),
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

    dataset_id = manifest["metadata"]["dataset"]
    primary_direction = PRIMARY_DIRECTIONS.get(dataset_id)
    models: list[dict[str, Any]] = []
    for provider in providers:
        item = summary[provider]
        total_cost = item["total_cost_usd"]
        quality = item["quality_by_labeled_direction"]
        if primary_direction is not None:
            headline = quality.get(primary_direction[0])
            headline_label = primary_direction[1]
        else:
            labeled = [metric for metric in quality.values() if metric.get("f1") is not None]
            headline = {
                metric_name: sum(metric[metric_name] for metric in labeled) / len(labeled)
                for metric_name in ("precision", "recall", "f1", "accuracy")
            }
            headline_label = "Macro average"
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
                "headline": headline,
                "headlineLabel": headline_label,
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
        "dataset": dataset_id,
        "datasetName": DATASET_NAMES.get(dataset_id, dataset_id),
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
    benchmarks = [export_run(path) for path in args.run]
    provider_ids = sorted({model["id"] for item in benchmarks for model in item["models"]})
    aggregate_models = []
    for provider_id in provider_ids:
        models = [
            model
            for benchmark in benchmarks
            for model in benchmark["models"]
            if model["id"] == provider_id
        ]
        aggregate_models.append(
            {
                "id": provider_id,
                "name": MODEL_NAMES.get(provider_id, provider_id),
                "promptTokens": sum(model["promptTokens"] for model in models),
                "completionTokens": sum(model["completionTokens"] for model in models),
                "totalTokens": sum(
                    model["promptTokens"] + model["completionTokens"] for model in models
                ),
                "costUsd": sum(model["costUsd"] for model in models),
                "costIsLowerBound": any(model["costIsLowerBound"] for model in models),
            }
        )
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "privacy": "Aggregate metrics only; no prompts, responses, API keys, or case identifiers.",
        "totals": {
            "datasetCount": len(benchmarks),
            "caseCount": sum(item["caseCount"] for item in benchmarks),
            "pairedCompleted": sum(item["pairedCompleted"] for item in benchmarks),
            "promptTokens": sum(model["promptTokens"] for model in aggregate_models),
            "completionTokens": sum(model["completionTokens"] for model in aggregate_models),
            "totalTokens": sum(model["totalTokens"] for model in aggregate_models),
            "costUsd": sum(model["costUsd"] for model in aggregate_models),
            "costIsLowerBound": any(model["costIsLowerBound"] for model in aggregate_models),
            "models": aggregate_models,
        },
        "benchmarks": benchmarks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {len(payload['benchmarks'])} benchmark(s) to {args.output}")


if __name__ == "__main__":
    main()
