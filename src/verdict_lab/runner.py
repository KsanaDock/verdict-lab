from __future__ import annotations

import itertools
import json
import random
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import httpx

from .adapters.base import ModerationAdapter
from .models import ModelResult, ModerationCase, RiskDirection, Usage


def _atomic_json(
    path: Path,
    value: object,
    *,
    retries: int = 6,
    retry_delay: float = 0.05,
) -> bool:
    """Write JSON safely, tolerating transient Windows file locks.

    The temporary file is deliberately retained when both replacement and the
    direct-write fallback are blocked, so the newest summary can still be
    recovered. Callers decide whether a failed metadata write is fatal.
    """
    payload = json.dumps(value, ensure_ascii=False, indent=2)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(payload, encoding="utf-8")
    except PermissionError:
        try:
            path.write_text(payload, encoding="utf-8")
        except PermissionError:
            return False
        return True
    for retry in range(max(1, retries)):
        try:
            temporary.replace(path)
            return True
        except PermissionError:
            if retry + 1 < max(1, retries):
                time.sleep(retry_delay * (2**retry))

    # Some Windows programs allow an existing file to be written but prevent
    # os.replace while they are previewing it. This fallback keeps the run alive.
    try:
        path.write_text(payload, encoding="utf-8")
    except PermissionError:
        return False
    try:
        temporary.unlink(missing_ok=True)
    except PermissionError:
        pass
    return True


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * fraction)))
    return ordered[index]


def _direction_metrics(
    group: list[ModelResult], cases: dict[str, ModerationCase], threshold: float
) -> dict[str, dict[str, float | int | None]]:
    direction_ids = sorted({direction_id for case in cases.values() for direction_id in case.gold})
    metrics: dict[str, dict[str, float | int | None]] = {}
    for direction_id in direction_ids:
        tp = tn = fp = fn = missing = 0
        for result in group:
            case = cases.get(result.case_id)
            if case is None or direction_id not in case.gold:
                continue
            score = result.scores.get(direction_id)
            if score is None:
                missing += 1
                continue
            predicted = score >= threshold
            actual = case.gold[direction_id]
            if predicted and actual:
                tp += 1
            elif predicted and not actual:
                fp += 1
            elif not predicted and actual:
                fn += 1
            else:
                tn += 1
        scored = tp + tn + fp + fn
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and precision + recall
            else None
        )
        metrics[direction_id] = {
            "labeled_cases": scored + missing,
            "scored_cases": scored,
            "missing_predictions": missing,
            "tp": tp,
            "tn": tn,
            "fp": fp,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "accuracy": (tp + tn) / scored if scored else None,
        }
    return metrics


def _build_summary(
    results: list[ModelResult],
    cases: dict[str, ModerationCase],
    threshold: float,
    attempts: list[ModelResult] | None = None,
    expected_providers: Iterable[str] | None = None,
) -> dict[str, object]:
    all_attempts = attempts if attempts is not None else results
    providers = sorted(
        set(expected_providers or ()) | {item.adapter_id or item.provider for item in all_attempts}
    )
    summary: dict[str, object] = {}
    for provider in providers:
        latest_group = [item for item in results if (item.adapter_id or item.provider) == provider]
        attempt_group = [item for item in all_attempts if (item.adapter_id or item.provider) == provider]
        known_costs = [item.cost_usd for item in attempt_group if item.cost_usd is not None]
        latencies = [item.latency_ms for item in attempt_group if item.status != "provider_error"]
        completed = sum(item.status == "ok" for item in latest_group)
        summary[provider] = {
            "expected_cases": len(cases),
            "completed_cases": completed,
            "remaining_cases": len(cases) - completed,
            "attempts": len(attempt_group),
            "failed_attempts": sum(item.status != "ok" for item in attempt_group),
            "total_cost_usd": (
                sum(known_costs) if len(known_costs) == len(attempt_group) else None
            ),
            "known_cost_subtotal_usd": sum(known_costs),
            "unknown_cost_attempts": len(attempt_group) - len(known_costs),
            "prompt_tokens": sum(item.usage.prompt_tokens or 0 for item in attempt_group),
            "completion_tokens": sum(item.usage.completion_tokens or 0 for item in attempt_group),
            "prompt_cache_hit_tokens": sum(
                item.usage.prompt_cache_hit_tokens or 0 for item in attempt_group
            ),
            "prompt_cache_miss_tokens": sum(
                item.usage.prompt_cache_miss_tokens or 0 for item in attempt_group
            ),
            "latency_ms": {
                "p50": _percentile(latencies, 0.50),
                "p95": _percentile(latencies, 0.95),
                "p99": _percentile(latencies, 0.99),
            },
            "quality_by_labeled_direction": _direction_metrics(latest_group, cases, threshold),
        }
    return summary


def _result_from_record(record: dict[str, Any]) -> ModelResult:
    field_names = {
        "case_id", "provider", "model", "status", "scores", "probability_source",
        "selected_directions", "latency_ms", "cost_usd", "cost_source", "errors", "adapter_id",
    }
    values = {key: record[key] for key in field_names if key in record}
    values["usage"] = Usage(**record.get("usage", {}))
    values["raw_response"] = {}
    return ModelResult(**values)


def _read_attempts(
    path: Path,
) -> tuple[list[ModelResult], dict[tuple[str, str], ModelResult], dict[tuple[str, str], int]]:
    attempts: list[ModelResult] = []
    latest: dict[tuple[str, str], ModelResult] = {}
    counts: dict[tuple[str, str], int] = {}
    if not path.exists():
        return attempts, latest, counts
    for line_number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            result = _result_from_record(record)
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError(f"invalid results.jsonl line {line_number}: {exc}") from exc
        if result.adapter_id is None:
            result.adapter_id = "jev" if result.provider == "openrouter" else result.provider
        key = (result.case_id, result.adapter_id)
        attempts.append(result)
        latest[key] = result
        counts[key] = max(counts.get(key, 0), int(record.get("attempt", counts.get(key, 0) + 1)))
    return attempts, latest, counts


def _exception_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            body: Any = exc.response.json()
        except (ValueError, json.JSONDecodeError):
            body = exc.response.text[:2000]
        return {"http_status": exc.response.status_code, "error": body}
    return {"error_type": type(exc).__name__, "message": str(exc)}


def _provider_pause_reason(exc: Exception) -> str | None:
    if not isinstance(exc, httpx.HTTPStatusError):
        return None
    text = exc.response.text.lower()
    if exc.response.status_code == 402 or any(
        term in text for term in ("insufficient", "quota", "credit", "balance")
    ):
        return "billing_or_quota"
    if exc.response.status_code in {401, 403}:
        return "authentication_or_permission"
    if exc.response.status_code == 429:
        return "rate_limit_or_quota"
    return None


def _one_line(value: str, limit: int = 1000) -> str:
    return " ".join(value.split())[:limit]


def _append_error_log(
    path: Path,
    result: ModelResult,
    attempt: int,
    pause_reason: str | None,
) -> None:
    details = _one_line("; ".join(result.errors) or "unknown error")
    line = (
        f"{datetime.now(timezone.utc).isoformat()} "
        f"case_id={result.case_id} adapter={result.adapter_id or result.provider} "
        f"provider={result.provider} model={result.model} attempt={attempt} "
        f"status={result.status} pause_reason={pause_reason or '-'} error={details}\n"
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()


def _safe_case_id(case_id: str) -> str:
    return case_id.replace(":", "_").replace("/", "_").replace("\\", "_")


def run_comparison(
    cases: Iterable[ModerationCase],
    adapters: dict[str, ModerationAdapter],
    directions: list[RiskDirection],
    threshold: float,
    output_root: str | Path = "runs",
    limit: int | None = None,
    seed: int = 20260920,
    run_metadata: dict[str, object] | None = None,
    resume_dir: str | Path | None = None,
    snapshots: dict[str, bytes] | None = None,
) -> Path:
    if resume_dir is None:
        run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        run_dir = Path(output_root) / run_id
        run_dir.mkdir(parents=True)
        selected_cases = list(itertools.islice(cases, limit)) if limit is not None else list(cases)
        if not selected_cases:
            raise ValueError("no cases selected")
        (run_dir / "cases.jsonl").write_text(
            "".join(json.dumps(asdict(case), ensure_ascii=False) + "\n" for case in selected_cases),
            encoding="utf-8",
        )
        manifest = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
            "providers": list(adapters),
            "threshold": threshold,
            "direction_ids": [item.id for item in directions],
            "seed": seed,
            "case_count": len(selected_cases),
            "error_log": "errors.log",
            "metadata": run_metadata or {},
        }
        if not _atomic_json(run_dir / "manifest.json", manifest):
            raise PermissionError(f"cannot write run manifest: {run_dir / 'manifest.json'}")
        for name, content in (snapshots or {}).items():
            (run_dir / name).write_bytes(content)
    else:
        run_dir = Path(resume_dir)
        if not run_dir.is_dir():
            raise ValueError(f"resume directory does not exist: {run_dir}")
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        if set(manifest["providers"]) != set(adapters):
            raise ValueError("resume providers do not match the original run")
        if manifest["direction_ids"] != [item.id for item in directions]:
            raise ValueError("resume taxonomy directions do not match the original run")
        if float(manifest["threshold"]) != threshold:
            raise ValueError("resume threshold does not match the original run")
        selected_cases = [
            ModerationCase(**json.loads(line))
            for line in (run_dir / "cases.jsonl").read_text(encoding="utf-8").split("\n")
            if line.strip()
        ]
        seed = int(manifest["seed"])
        manifest["status"] = "running"
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        if not _atomic_json(run_dir / "manifest.json", manifest):
            raise PermissionError(f"cannot update run manifest: {run_dir / 'manifest.json'}")

    raw_dir = run_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    error_log_path = run_dir / "errors.log"
    error_log_path.touch(exist_ok=True)
    result_path = run_dir / "results.jsonl"
    attempts, latest, attempt_counts = _read_attempts(result_path)
    evaluated_cases = {case.case_id: case for case in selected_cases}
    disabled_providers: set[str] = set()
    pause_reasons: dict[str, str] = {}
    rng = random.Random(seed)
    total_pairs = len(selected_cases) * len(adapters)

    def completed_pairs() -> int:
        return sum(
            (case.case_id, name) in latest and latest[(case.case_id, name)].status == "ok"
            for case in selected_cases
            for name in adapters
        )

    starting_completed = completed_pairs()
    mode = "resume" if resume_dir is not None else "new"
    print(
        f"[VerdictLab] mode={mode} run={run_dir} cases={len(selected_cases)} "
        f"models={','.join(adapters)} total_pairs={total_pairs}",
        flush=True,
    )
    print(
        f"[VerdictLab] completed={starting_completed}/{total_pairs} "
        f"remaining={total_pairs - starting_completed} errors={error_log_path}",
        flush=True,
    )

    summary_write_warning_shown = False

    def persist_progress() -> bool:
        nonlocal summary_write_warning_shown
        saved = _atomic_json(
            run_dir / "summary.json",
            _build_summary(list(latest.values()), evaluated_cases, threshold, attempts, adapters),
            retries=1 if summary_write_warning_shown else 6,
        )
        if not saved and not summary_write_warning_shown:
            warning = (
                "summary.json is locked; results.jsonl is safe and the run will continue. "
                "Close any editor or preview that has summary.json open."
            )
            with error_log_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    f"{datetime.now(timezone.utc).isoformat()} "
                    f"event=summary_write_blocked error={warning}\n"
                )
                handle.flush()
            print(f"[VerdictLab][WARNING] {warning}", flush=True)
            summary_write_warning_shown = True
        elif saved:
            summary_write_warning_shown = False
        return saved

    try:
        with result_path.open("a", encoding="utf-8") as result_file:
            for case in selected_cases:
                names = list(adapters)
                rng.shuffle(names)
                for name in names:
                    key = (case.case_id, name)
                    if name in disabled_providers or (key in latest and latest[key].status == "ok"):
                        continue
                    attempt_number = attempt_counts.get(key, 0) + 1
                    pause_reason: str | None = None
                    try:
                        result = adapters[name].evaluate(case, directions, threshold)
                    except Exception as exc:
                        pause_reason = _provider_pause_reason(exc)
                        result = ModelResult(
                            case_id=case.case_id,
                            provider=name,
                            model=str(getattr(adapters[name], "model", "unknown")),
                            status="provider_error",
                            scores={},
                            probability_source="unavailable",
                            selected_directions=[],
                            latency_ms=0,
                            usage=Usage(),
                            cost_usd=None,
                            cost_source="unknown",
                            raw_response=_exception_payload(exc),
                            errors=[f"{type(exc).__name__}: {exc}"],
                        )
                    raw_path = raw_dir / (
                        f"{_safe_case_id(case.case_id)}__{name}__attempt-{attempt_number}.json"
                    )
                    result.adapter_id = name
                    raw_path.write_text(
                        json.dumps(result.raw_response, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    record = result.to_dict(include_raw=False)
                    record.update({
                        "attempt": attempt_number,
                        "recorded_at": datetime.now(timezone.utc).isoformat(),
                        "raw_response_ref": str(raw_path.relative_to(run_dir)),
                    })
                    result_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                    result_file.flush()
                    attempts.append(result)
                    latest[key] = result
                    attempt_counts[key] = attempt_number
                    persist_progress()
                    completed = completed_pairs()
                    cost = "unknown" if result.cost_usd is None else f"${result.cost_usd:.9f}"
                    selected = ",".join(result.selected_directions) or "-"
                    print(
                        f"[{completed}/{total_pairs}] {result.status.upper()} "
                        f"case={case.case_id} model={name} attempt={attempt_number} "
                        f"latency={result.latency_ms:.0f}ms cost={cost} selected={selected}",
                        flush=True,
                    )
                    if result.status != "ok":
                        _append_error_log(error_log_path, result, attempt_number, pause_reason)
                        print(
                            f"[VerdictLab][ERROR] model={name} case={case.case_id} "
                            f"details={_one_line('; '.join(result.errors), 500)}",
                            flush=True,
                        )
                    if pause_reason:
                        disabled_providers.add(name)
                        pause_reasons[name] = pause_reason
                        print(
                            f"[VerdictLab][PAUSED] model={name} reason={pause_reason}; "
                            f"the other model will continue. Resume later with: "
                            f"verdict-lab compare --resume \"{run_dir}\"",
                            flush=True,
                        )
    except KeyboardInterrupt:
        with error_log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                f"{datetime.now(timezone.utc).isoformat()} event=run_interrupted "
                f"error=KeyboardInterrupt resume_dir={run_dir}\n"
            )
        print(
            f"\n[VerdictLab][INTERRUPTED] saved progress. Resume with: "
            f"verdict-lab compare --resume \"{run_dir}\"",
            flush=True,
        )
        raise
    finally:
        persist_progress()
        complete = all(
            (case.case_id, name) in latest and latest[(case.case_id, name)].status == "ok"
            for case in selected_cases
            for name in adapters
        )
        manifest["status"] = "complete" if complete else "paused"
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        manifest["paused_providers"] = sorted(disabled_providers)
        manifest["pause_reasons"] = pause_reasons
        if not _atomic_json(run_dir / "manifest.json", manifest):
            warning = (
                "manifest.json is locked; results.jsonl and summary.json were saved, "
                "but the final manifest status could not be updated."
            )
            with error_log_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    f"{datetime.now(timezone.utc).isoformat()} "
                    f"event=manifest_write_blocked error={warning}\n"
                )
            print(f"[VerdictLab][WARNING] {warning}", flush=True)
        final_completed = completed_pairs()
        final_label = "DONE" if complete else "PAUSED"
        print(
            f"[VerdictLab][{final_label}] completed={final_completed}/{total_pairs} "
            f"remaining={total_pairs - final_completed} run={run_dir} errors={error_log_path}",
            flush=True,
        )
    return run_dir
