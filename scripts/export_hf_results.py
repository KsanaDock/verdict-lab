from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


DATASET_FILES = {
    "aegis": "aegis.jsonl",
    "chineseharm": "chineseharm.jsonl",
    "cold": "cold.jsonl",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_successful_results(run_dir: Path) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    with (run_dir / "results.jsonl").open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            record = json.loads(line)
            adapter = record.get("adapter_id") or record["provider"]
            latest[(record["case_id"], adapter)] = record

    rows = []
    for record in latest.values():
        if record.get("status") != "ok":
            continue
        public_record = {
            key: value
            for key, value in record.items()
            if key not in {"raw_response_ref", "errors"}
        }
        rows.append(public_record)
    return sorted(rows, key=lambda item: (item["case_id"], item.get("adapter_id", "")))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as target:
        for row in rows:
            target.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def dataset_card(counts: dict[str, int]) -> str:
    return f"""---
pretty_name: VerdictLab Results
language:
- zh
- en
license: other
task_categories:
- text-classification
tags:
- content-safety
- benchmark
- moderation
---

# VerdictLab Results

Final successful model-evaluation records from [VerdictLab](https://github.com/KsanaDock/verdict-lab), comparing OpenRouter Jev 1.13 and DeepSeek Flash.

| File | Dataset | Rows |
| --- | --- | ---: |
| `data/chineseharm.jsonl` | [ChineseHarm-Bench](https://github.com/zjunlp/ChineseHarm-bench) | {counts.get('chineseharm', 0):,} |
| `data/cold.jsonl` | [COLDataset](https://github.com/thu-coai/COLDataset) | {counts.get('cold', 0):,} |
| `data/aegis.jsonl` | [Aegis AI Content Safety Dataset 2.0](https://huggingface.co/datasets/nvidia/Aegis-AI-Content-Safety-Dataset-2.0) | {counts.get('aegis', 0):,} |

Each row is one final successful `sample × model` result. Failed requests and superseded retries are excluded. The published files contain case identifiers, normalized risk scores, selected directions, latency, token usage, cache usage, and cost. They do not contain source prompts, dataset text, provider raw responses, or API credentials.

`benchmarks.json` contains the aggregate metrics used by the [public dashboard](https://ksanadock.github.io/verdict-lab/).

Source datasets remain governed by their respective licenses and terms. This repository publishes derived evaluation metadata only.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Export public-safe VerdictLab results for Hugging Face")
    parser.add_argument("--run", action="append", required=True, type=Path)
    parser.add_argument("--dashboard", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    data_dir = args.output / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for run_dir in args.run:
        manifest = read_json(run_dir / "manifest.json")
        dataset = manifest["metadata"]["dataset"]
        rows = latest_successful_results(run_dir)
        write_jsonl(data_dir / DATASET_FILES[dataset], rows)
        counts[dataset] = len(rows)

    shutil.copyfile(args.dashboard, args.output / "benchmarks.json")
    (args.output / "README.md").write_text(dataset_card(counts), encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(args.output), "rows": counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
