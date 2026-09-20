from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from .models import ModerationCase


CHINESE_HARM_DIRECTIONS = {
    "博彩": "gambling",
    "低俗色情": "pornography",
    "谩骂引战": "abuse_harassment",
    "欺诈": "fraud",
    "黑产广告": "illicit_advertising",
}
CHINESE_HARM_LABELS = {*CHINESE_HARM_DIRECTIONS, "不违规"}

AEGIS_CATEGORY_DIRECTIONS = {
    "Hate/Identity Hate": "hate_identity",
    "Sexual": "sexual",
    "Suicide and Self Harm": "self_harm",
    "Violence": "violence",
    "Guns and Illegal Weapons": "guns_illegal_weapons",
    "Threat": "threat",
    "PII/Privacy": "pii_privacy",
    "Sexual (minor)": "sexual_minors",
    "Criminal Planning/Confessions": "criminal_planning",
    "Harassment": "harassment",
    "Controlled/Regulated Substances": "controlled_substances",
    "Profanity": "profanity",
    "Illegal Activity": "illegal_activity",
    "Immoral/Unethical": "immoral_unethical",
    "Unauthorized Advice": "unauthorized_advice",
    "Political/Misinformation/Conspiracy": "political_misinformation",
    "Fraud/Deception": "fraud_deception",
    "Copyright/Trademark/Plagiarism": "copyright_plagiarism",
    "High Risk Gov Decision Making": "high_risk_government_decision",
    "Malware": "malware",
    "Manipulation": "manipulation",
    "Needs Caution": "needs_caution",
    "Other": "other",
}


def load_chinese_harm(path: str | Path, split: str = "benchmark") -> Iterable[ModerationCase]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("ChineseHarm-Bench file must contain a JSON array")
    for index, row in enumerate(rows):
        text = row.get("文本")
        label = row.get("标签")
        if not isinstance(text, str) or not isinstance(label, str):
            raise ValueError(f"invalid ChineseHarm-Bench row at index {index}")
        if label not in CHINESE_HARM_LABELS:
            raise ValueError(f"unknown ChineseHarm-Bench label at index {index}: {label}")
        # The released benchmark is single-label. Only its five native harmful
        # directions are treated as known true/false; broader project directions
        # such as advertising or off-site diversion remain unlabelled.
        gold = {direction_id: False for direction_id in CHINESE_HARM_DIRECTIONS.values()}
        if label != "不违规":
            gold[CHINESE_HARM_DIRECTIONS[label]] = True
        yield ModerationCase(
            case_id=f"chineseharm:{split}:{index}",
            content=text,
            dataset="ChineseHarm-Bench",
            split=split,
            source_label=label,
            gold=gold,
        )


def load_cold(path: str | Path) -> Iterable[ModerationCase]:
    source = Path(path)
    split = source.stem
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader):
            text = row.get("TEXT")
            label = row.get("label")
            if not isinstance(text, str) or label not in {"0", "1"}:
                raise ValueError(f"invalid COLDataset row at index {index}")
            fine = row.get("fine-grained-label")
            gold: dict[str, bool] = {}
            if fine in {"1", "2"}:
                gold["abuse_harassment"] = True
            elif fine in {"0", "3"}:
                gold["abuse_harassment"] = False
            elif label == "1":
                gold["abuse_harassment"] = True
            elif label == "0":
                gold["abuse_harassment"] = False
            row_id = row.get("") or str(index)
            yield ModerationCase(
                case_id=f"cold:{split}:{row_id}",
                content=text,
                dataset="COLDataset",
                split=split,
                source_label=fine or label,
                gold=gold,
                metadata={"topic": row.get("topic"), "binary_label": label, "fine_label": fine},
            )


def load_aegis(path: str | Path, split: str | None = None) -> Iterable[ModerationCase]:
    source = Path(path)
    split_name = split or source.stem
    rows = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Aegis file must contain a JSON array")
    category_ids = set(AEGIS_CATEGORY_DIRECTIONS.values())
    for index, row in enumerate(rows):
        prompt = row.get("prompt")
        response = row.get("response")
        prompt_label = row.get("prompt_label")
        response_label = row.get("response_label")
        if not isinstance(prompt, str) or prompt_label not in {"safe", "unsafe"}:
            raise ValueError(f"invalid Aegis row at index {index}")
        if prompt == "REDACTED" and row.get("reconstruction_id_if_redacted") is not None:
            continue
        if response_label not in {None, "safe", "unsafe"}:
            raise ValueError(f"invalid Aegis response label at index {index}: {response_label}")
        raw_categories = [
            item.strip() for item in (row.get("violated_categories") or "").split(",") if item.strip()
        ]
        unknown = set(raw_categories) - set(AEGIS_CATEGORY_DIRECTIONS)
        if unknown:
            raise ValueError(f"unknown Aegis categories at index {index}: {sorted(unknown)}")
        present = {AEGIS_CATEGORY_DIRECTIONS[item] for item in raw_categories}
        gold = {direction_id: direction_id in present for direction_id in category_ids}
        gold["unsafe_overall"] = prompt_label == "unsafe" or response_label == "unsafe"
        content = f"User prompt:\n{prompt}"
        if isinstance(response, str) and response:
            content += f"\n\nAssistant response:\n{response}"
        row_id = row.get("id") or str(index)
        yield ModerationCase(
            case_id=f"aegis:{split_name}:{row_id}",
            content=content,
            dataset="Aegis-AI-Content-Safety-Dataset-2.0",
            split=split_name,
            source_label="unsafe" if gold["unsafe_overall"] else "safe",
            gold=gold,
            metadata={
                "language": "en",
                "task_mode": "conversation",
                "prompt_label": prompt_label,
                "response_label": response_label,
                "prompt_label_source": row.get("prompt_label_source"),
                "response_label_source": row.get("response_label_source"),
                "violated_categories": raw_categories,
            },
        )
