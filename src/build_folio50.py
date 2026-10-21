#!/usr/bin/env python3
"""Build a deterministic 50-example subset from curated FOLIO validation data."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any


SEED = 42
TARGET_SIZE = 50
MIN_LONG_EXAMPLES = 10
LONG_PREMISE_THRESHOLD = 5
LABEL_QUOTAS = {"True": 17, "False": 17, "Uncertain": 16}

SOURCE_DATASET = "DSAVlab-UNIUD/FOLIO_validation-curated"
SOURCE_REVISION = "5d8ef8e26e04b77bc386482e3f7901e999a16113"
VALID_LABELS = frozenset(LABEL_QUOTAS)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "data" / "FOLIO_instances.jsonl"
DEFAULT_OUTPUT = ROOT / "data" / "folio50.jsonl"

CONCLUSION_ID_RE = re.compile(r"^concl_(.+)_([^_]+)$")
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


class DatasetError(RuntimeError):
    """Raised when the curated source cannot satisfy the subset contract."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Curated FOLIO JSONL (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Destination JSONL (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=SEED,
        help=f"Deterministic selection seed (default: {SEED})",
    )
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise DatasetError(
            f"Curated source file not found: {path}\n"
            "Expected FOLIO_instances.jsonl from "
            f"{SOURCE_DATASET} at revision {SOURCE_REVISION}."
        )

    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DatasetError(
                    f"Invalid JSON on line {line_number} of {path}: {exc}"
                ) from exc
            if not isinstance(row, dict):
                raise DatasetError(
                    f"Line {line_number} of {path} is not a JSON object."
                )
            row["_source_row_number"] = line_number
            rows.append(row)

    if not rows:
        raise DatasetError(f"Curated source file is empty: {path}")
    return rows


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def split_natural_language_premises(text: str) -> list[str]:
    """Split the curated story paragraph at its English sentence boundaries."""
    premises = [part.strip() for part in SENTENCE_BOUNDARY_RE.split(text.strip())]
    return [premise for premise in premises if premise]


def split_top_level_conjunctions(formula: str) -> list[str]:
    """Expose top-level conjuncts while retaining the exact source formula too."""
    parts: list[str] = []
    depth = 0
    start = 0

    for index, character in enumerate(formula):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "∧" and depth == 0:
            part = formula[start:index].strip()
            if part:
                parts.append(part)
            start = index + 1

    final_part = formula[start:].strip()
    if final_part:
        parts.append(final_part)
    return parts


def is_ambiguous(row: dict[str, Any]) -> bool:
    if bool(row.get("ambiguity")):
        return True

    # The curated file contains a few misspelled/alternate ambiguity metadata
    # keys. Treat any populated one as an ambiguity marker.
    for key, value in row.items():
        normalized_key = key.lower()
        if "ambigu" in normalized_key or "amnigu" in normalized_key:
            if value not in (None, False, "", "no", "false", "False"):
                return True
    return False


def resolve_label(row: dict[str, Any]) -> tuple[str, str]:
    """Use the curated label, including the source's documented fallback keys."""
    for field in ("label", "label_new", "label_z3"):
        value = row.get(field)
        if value in VALID_LABELS:
            return value, field
    raise DatasetError(
        f"No valid curated label for conclusion {row.get('id')!r}; "
        "checked label, label_new, and label_z3."
    )


def story_id_for_conclusion(conclusion_id: str) -> str:
    match = CONCLUSION_ID_RE.fullmatch(conclusion_id)
    if match is None:
        raise DatasetError(f"Unexpected conclusion ID format: {conclusion_id!r}")
    return f"story_{match.group(1)}"


def useful_curation_metadata(row: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "corrected",
        "ambiguity",
        "ambiguity_explanation",
        "ambiguity_commentary",
        "amniguity_explanation",
        "correction_explanation",
        "corerection_explanation",
        "correction",
        "note",
        "NLI_requires_more_info",
        "label_old",
        "label_old_z3",
        "label_z3",
    )
    return {field: row[field] for field in fields if field in row}


def build_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stories = {
        row["id"]: row
        for row in rows
        if str(row.get("id", "")).startswith("story_")
    }
    if not stories:
        raise DatasetError("No story_* records found in the curated source.")

    candidates: list[dict[str, Any]] = []
    seen_conclusion_ids: set[str] = set()

    for row in rows:
        conclusion_id = str(row.get("id", ""))
        if not conclusion_id.startswith("concl_"):
            continue
        if conclusion_id in seen_conclusion_ids:
            raise DatasetError(f"Duplicate conclusion ID: {conclusion_id}")
        seen_conclusion_ids.add(conclusion_id)

        story_id = story_id_for_conclusion(conclusion_id)
        try:
            story = stories[story_id]
        except KeyError as exc:
            raise DatasetError(
                f"Conclusion {conclusion_id} has no matching {story_id} record."
            ) from exc

        premises_text = story.get("NL_sentence")
        premises_fol_combined = story.get("FOL_sentence")
        conclusion_text = row.get("NL_sentence")
        conclusion_fol = row.get("FOL_sentence")
        required_strings = {
            "story.NL_sentence": premises_text,
            "story.FOL_sentence": premises_fol_combined,
            "conclusion.NL_sentence": conclusion_text,
            "conclusion.FOL_sentence": conclusion_fol,
        }
        missing = [name for name, value in required_strings.items() if not value]
        if missing:
            raise DatasetError(
                f"{conclusion_id} is missing required fields: {', '.join(missing)}"
            )

        label, label_field = resolve_label(row)
        premises = split_natural_language_premises(str(premises_text))
        premises_fol = split_top_level_conjunctions(str(premises_fol_combined))
        if not premises or not premises_fol:
            raise DatasetError(f"Could not parse premises for {conclusion_id}.")

        candidate = {
            "source_dataset": SOURCE_DATASET,
            "source_revision": SOURCE_REVISION,
            "source_file": "FOLIO_instances.jsonl",
            "source_story_id": story_id,
            "source_example_id": conclusion_id,
            "source_story_row_number": story["_source_row_number"],
            "source_example_row_number": row["_source_row_number"],
            "source_label_field": label_field,
            "premises": premises,
            "premises_text_combined": str(premises_text),
            "conclusion": str(conclusion_text),
            "premises_fol": premises_fol,
            "premises_fol_combined": str(premises_fol_combined),
            "conclusion_fol": str(conclusion_fol),
            "label": label,
            "premise_count": len(premises),
            "num_premises": len(premises),
            "has_at_least_5_premises": len(premises) >= LONG_PREMISE_THRESHOLD,
            "is_ambiguous": is_ambiguous(story) or is_ambiguous(row),
            "curation_metadata": {
                "story": useful_curation_metadata(story),
                "conclusion": useful_curation_metadata(row),
                "story_fol_old": story.get("FOL_sentence_old"),
                "conclusion_fol_old": row.get("FOL_sentence_old"),
            },
        }
        candidates.append(candidate)

    if not candidates:
        raise DatasetError("No concl_* records found in the curated source.")
    return candidates


def select_examples(
    candidates: list[dict[str, Any]], seed: int
) -> list[dict[str, Any]]:
    """Select balanced examples, preferring only unambiguous candidates."""
    rng = random.Random(seed)
    shuffled = list(candidates)
    rng.shuffle(shuffled)

    unambiguous = [row for row in shuffled if not row["is_ambiguous"]]
    selected: list[dict[str, Any]] = []

    for label, quota in LABEL_QUOTAS.items():
        preferred = [row for row in unambiguous if row["label"] == label]
        fallback = [
            row for row in shuffled if row["label"] == label and row["is_ambiguous"]
        ]
        available = preferred + fallback
        if len(available) < quota:
            raise DatasetError(
                f"Need {quota} {label} examples, found {len(available)}."
            )
        selected.extend(available[:quota])

    # A deterministic same-label swap guarantees the >=5-premise constraint
    # without changing the requested class balance.
    long_count = sum(row["has_at_least_5_premises"] for row in selected)
    if long_count < MIN_LONG_EXAMPLES:
        selected_ids = {row["source_example_id"] for row in selected}
        for label in LABEL_QUOTAS:
            replacements = [
                row
                for row in unambiguous
                if row["label"] == label
                and row["has_at_least_5_premises"]
                and row["source_example_id"] not in selected_ids
            ]
            replaceable = [
                row
                for row in reversed(selected)
                if row["label"] == label and not row["has_at_least_5_premises"]
            ]
            for old, new in zip(replaceable, replacements):
                index = selected.index(old)
                selected[index] = new
                selected_ids.remove(old["source_example_id"])
                selected_ids.add(new["source_example_id"])
                long_count += 1
                if long_count >= MIN_LONG_EXAMPLES:
                    break
            if long_count >= MIN_LONG_EXAMPLES:
                break

    selected.sort(key=lambda row: row["source_example_row_number"])
    for index, row in enumerate(selected, start=1):
        row["id"] = f"folio50-{index:03d}"
        # Compatibility with the existing Qwen runner's result schema.
        row["source_index"] = row["source_example_row_number"] - 1
    return selected


def validate(examples: list[dict[str, Any]]) -> None:
    errors: list[str] = []
    if len(examples) != TARGET_SIZE:
        errors.append(f"expected exactly {TARGET_SIZE} examples, got {len(examples)}")

    ids = [row["id"] for row in examples]
    source_ids = [row["source_example_id"] for row in examples]
    if len(ids) != len(set(ids)):
        errors.append("generated IDs are not unique")
    if len(source_ids) != len(set(source_ids)):
        errors.append("source example IDs are not unique")

    label_counts = Counter(row["label"] for row in examples)
    if label_counts != Counter(LABEL_QUOTAS):
        errors.append(
            f"label counts must be {LABEL_QUOTAS}, got {dict(label_counts)}"
        )

    long_count = sum(row["premise_count"] >= LONG_PREMISE_THRESHOLD for row in examples)
    if long_count < MIN_LONG_EXAMPLES:
        errors.append(
            f"need at least {MIN_LONG_EXAMPLES} examples with "
            f">={LONG_PREMISE_THRESHOLD} premises, got {long_count}"
        )

    for row in examples:
        if row["premise_count"] != len(row["premises"]):
            errors.append(f"{row['id']}: premise_count does not match premises")
        if not row["premises_fol_combined"] or not row["conclusion_fol"]:
            errors.append(f"{row['id']}: missing FOL formalization")

    if errors:
        raise DatasetError("Validation failed:\n- " + "\n- ".join(errors))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as destination:
        for row in rows:
            destination.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def print_summary(examples: list[dict[str, Any]], output: Path) -> None:
    counts = Counter(row["label"] for row in examples)
    premise_counts = [row["premise_count"] for row in examples]
    long_count = sum(count >= LONG_PREMISE_THRESHOLD for count in premise_counts)
    ambiguous_count = sum(row["is_ambiguous"] for row in examples)

    print(f"Created {len(examples)} examples: {output}")
    print(
        "Classes: "
        + ", ".join(f"{label.upper()}={counts[label]}" for label in LABEL_QUOTAS)
    )
    print(
        "Premises: "
        f"min={min(premise_counts)}, max={max(premise_counts)}, "
        f"mean={statistics.mean(premise_counts):.2f}, "
        f"median={statistics.median(premise_counts):g}, "
        f">={LONG_PREMISE_THRESHOLD}={long_count}"
    )
    print(f"Ambiguous selected: {ambiguous_count}")
    print(f"SHA-256: {sha256(output)}")


def main() -> None:
    args = parse_args()
    rows = read_jsonl(args.input)
    candidates = build_candidates(rows)
    examples = select_examples(candidates, args.seed)
    validate(examples)
    write_jsonl(args.output, examples)
    print_summary(examples, args.output)


if __name__ == "__main__":
    main()
