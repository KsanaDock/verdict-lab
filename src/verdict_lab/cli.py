from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import sys
from pathlib import Path

from .adapters import DeepSeekFlashAdapter, OpenRouterJevAdapter
from .costs import load_pricing
from .datasets import load_aegis, load_chinese_harm, load_cold
from .models import ModerationCase
from .runner import run_comparison
from .taxonomy import load_taxonomy


def _load_dotenv(path: str | Path = ".env") -> None:
    source = Path(path)
    if not source.is_file():
        return
    for line in source.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        name = name.strip()
        if name.isidentifier():
            os.environ.setdefault(name, value.strip().strip('"').strip("'"))


def _cases(kind: str, path: str):
    if kind == "cold":
        return load_cold(path)
    if kind == "chineseharm":
        return load_chinese_harm(path)
    return load_aegis(path)


def _default_taxonomy(dataset: str | None) -> Path:
    return Path("config/taxonomy-aegis.json" if dataset == "aegis" else "config/taxonomy.json")


def _saved_cases(run_dir: Path) -> list[ModerationCase]:
    return [
        ModerationCase(**json.loads(line))
        # JSON strings may legally contain a literal U+2028 line separator.
        # JSONL records are separated by LF, so split only on that character.
        for line in (run_dir / "cases.jsonl").read_text(encoding="utf-8").split("\n")
        if line.strip()
    ]


def _verify_hash(parser: argparse.ArgumentParser, path: Path, expected: str | None, label: str) -> None:
    if expected is None:
        return
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        parser.error(f"{label} hash differs from the original run; refusing unsafe resume")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    _load_dotenv()
    parser = argparse.ArgumentParser(prog="verdict-lab")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect_parser = sub.add_parser("inspect", help="Inspect normalized dataset cases without calling a model")
    inspect_parser.add_argument("--dataset", choices=["cold", "chineseharm", "aegis"], required=True)
    inspect_parser.add_argument("--path", required=True)
    inspect_parser.add_argument("--limit", type=int, default=3)
    compare = sub.add_parser("compare", help="Run Jev and DeepSeek on the same cases")
    compare.add_argument("--dataset", choices=["cold", "chineseharm", "aegis"])
    compare.add_argument("--path")
    compare.add_argument("--limit", type=int)
    compare.add_argument("--all", action="store_true", help="Run every evaluable case in the selected dataset")
    compare.add_argument("--resume", help="Existing run directory to resume in place")
    compare.add_argument("--taxonomy")
    compare.add_argument("--pricing", default="config/pricing.json")
    compare.add_argument("--output", default="runs")
    args = parser.parse_args()
    if args.command == "inspect":
        for case in itertools.islice(_cases(args.dataset, args.path), args.limit):
            print(json.dumps(case.__dict__, ensure_ascii=False, indent=2))
        return

    resume_dir = Path(args.resume) if args.resume else None
    if resume_dir is None:
        if not args.dataset or not args.path:
            parser.error("a new compare run requires --dataset and --path")
        if args.all and args.limit is not None:
            parser.error("use either --all or --limit, not both")
        selected_cases = _cases(args.dataset, args.path)
        limit = None if args.all else (10 if args.limit is None else args.limit)
        taxonomy_path = Path(args.taxonomy) if args.taxonomy else _default_taxonomy(args.dataset)
        pricing_path = Path(args.pricing)
        original_manifest = None
    else:
        if args.dataset or args.path or args.limit is not None or args.all:
            parser.error("--resume uses frozen cases; omit --dataset, --path, --limit, and --all")
        if not resume_dir.is_dir():
            parser.error(f"resume directory does not exist: {resume_dir}")
        original_manifest = json.loads((resume_dir / "manifest.json").read_text(encoding="utf-8"))
        selected_cases = _saved_cases(resume_dir)
        limit = None
        metadata = original_manifest.get("metadata", {})
        taxonomy_snapshot = resume_dir / "taxonomy.snapshot.json"
        pricing_snapshot = resume_dir / "pricing.snapshot.json"
        taxonomy_path = (
            taxonomy_snapshot
            if taxonomy_snapshot.exists()
            else (Path(args.taxonomy) if args.taxonomy else _default_taxonomy(metadata.get("dataset")))
        )
        pricing_path = pricing_snapshot if pricing_snapshot.exists() else Path(args.pricing)
        _verify_hash(parser, taxonomy_path, metadata.get("taxonomy_sha256"), "taxonomy")
        _verify_hash(parser, pricing_path, metadata.get("pricing_sha256"), "pricing")

    missing = [name for name in ("OPENROUTER_API_KEY", "DEEPSEEK_API_KEY") if not os.getenv(name)]
    if missing:
        parser.error(f"compare requires environment variables: {', '.join(missing)}")
    taxonomy_version, threshold, directions = load_taxonomy(taxonomy_path)
    pricing = load_pricing(pricing_path)
    adapters = {
        "jev": OpenRouterJevAdapter(os.getenv("OPENROUTER_API_KEY", ""), pricing),
        "deepseek": DeepSeekFlashAdapter(os.getenv("DEEPSEEK_API_KEY", ""), pricing),
    }
    run_metadata = None
    snapshots = None
    if resume_dir is None:
        dataset_path = Path(args.path)
        run_metadata = {
            "taxonomy_version": taxonomy_version,
            "taxonomy_sha256": hashlib.sha256(taxonomy_path.read_bytes()).hexdigest(),
            "pricing_snapshot_date": pricing["snapshot_date"],
            "pricing_sha256": hashlib.sha256(pricing_path.read_bytes()).hexdigest(),
            "dataset": args.dataset,
            "dataset_path": str(dataset_path.resolve()),
            "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
            "model_configs": {
                "jev": {"model": "typesafe/jev-1.13", "question_type": "noul"},
                "deepseek": {
                    "model": "deepseek-flash",
                    "thinking": "disabled",
                    "temperature": 0,
                    "response_format": "json_object",
                },
            },
        }
        snapshots = {
            "taxonomy.snapshot.json": taxonomy_path.read_bytes(),
            "pricing.snapshot.json": pricing_path.read_bytes(),
        }
    try:
        output = run_comparison(
            selected_cases,
            adapters,
            directions,
            threshold,
            args.output,
            limit,
            run_metadata=run_metadata,
            resume_dir=resume_dir,
            snapshots=snapshots,
        )
    finally:
        for adapter in adapters.values():
            adapter.close()
    print(output)


if __name__ == "__main__":
    main()
