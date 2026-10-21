import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from datasets import load_dataset


SEED = 42
TARGET_SIZE = 50
MIN_HARD_EXAMPLES = 10
HARD_PREMISE_THRESHOLD = 5

LABEL_QUOTAS = {
    "True": 17,
    "False": 17,
    "Uncertain": 16,
}

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"

RAW_PATH = RAW_DIR / "folio_validation.jsonl"
OUTPUT_PATH = DATA_DIR / "folio_50.jsonl"
METADATA_PATH = DATA_DIR / "folio_50_metadata.json"


def write_jsonl(path: Path, rows: list[dict]) -> None:
    """Write a list of dictionaries to a JSON Lines file."""
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def sha256(path: Path) -> str:
    """Calculate the SHA256 hash of a file."""
    digest = hashlib.sha256()

    with path.open("rb") as f:
        while chunk := f.read(8192):
            digest.update(chunk)

    return digest.hexdigest()


def main() -> None:
    """Download, select, and freeze the FOLIO benchmark subset."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading FOLIO validation dataset...")

    dataset = load_dataset(
        "benlipkin/folio",
        split="validation",
    )

    # Create directories if they don't exist

    rows = []

    for source_index, example in enumerate(dataset):
        row = dict(example)
        row["_source_index"] = source_index
        rows.append(row)

    # -------------------------------------------------------------
    # Save untouched source dataset locally
    # -------------------------------------------------------------

    raw_rows = []

    for row in rows:
        raw = {
            key: value
            for key, value in row.items()
            if key != "_source_index"
        }

        raw["_source_index"] = row["_source_index"]
        raw_rows.append(raw)

    write_jsonl(RAW_PATH, raw_rows)

    print(f"Saved raw validation snapshot → {RAW_PATH}")

    # -------------------------------------------------------------
    # Check source labels
    # -------------------------------------------------------------

    source_distribution = Counter(
        row["label"]
        for row in rows
    )

    print("\nSource label distribution:")
    for label, count in sorted(source_distribution.items()):
        print(f"  {label}: {count}")

    for label, quota in LABEL_QUOTAS.items():
        available = source_distribution[label]

        if available < quota:
            raise RuntimeError(
                f"Not enough '{label}' examples. "
                f"Need {quota}, found {available}."
            )

    # -------------------------------------------------------------
    # Deterministic shuffle
    # -------------------------------------------------------------

    rng = random.Random(SEED)
    rng.shuffle(rows)

    selected = []
    selected_indices = set()

    remaining_quota = LABEL_QUOTAS.copy()

    # -------------------------------------------------------------
    # STEP 1:
    # Guarantee at least 10 examples with >=5 premises.
    # -------------------------------------------------------------

    hard_candidates = [
        row
        for row in rows
        if len(row["premises"]) >= HARD_PREMISE_THRESHOLD
    ]

    for row in hard_candidates:
        if len(selected) >= MIN_HARD_EXAMPLES:
            break

        label = row["label"]

        selected.append(row)
        selected_indices.add(row["_source_index"])
        remaining_quota[label] -= 1

    hard_selected = sum(
        len(row["premises"]) >= HARD_PREMISE_THRESHOLD
        for row in selected
    )

    if hard_selected < MIN_HARD_EXAMPLES:
        raise RuntimeError(
            f"Could only select {hard_selected} hard examples; "
            f"need at least {MIN_HARD_EXAMPLES}."
        )

    # -------------------------------------------------------------
    # STEP 2:
    # Fill remaining label quotas.
    # -------------------------------------------------------------

    for label, quota_left in list(remaining_quota.items()):

        candidates = [
            row
            for row in rows
            if row["label"] == label
            and row["_source_index"] not in selected_indices
        ]

        if len(candidates) < quota_left:
            raise RuntimeError(
                f"Not enough remaining examples for {label}. "
                f"Need {quota_left}, found {len(candidates)}."
            )

        chosen = candidates[:quota_left]

        for row in chosen:
            selected.append(row)
            selected_indices.add(row["_source_index"])

    if len(selected) != TARGET_SIZE:
        raise RuntimeError(
            f"Expected {TARGET_SIZE} examples, "
            f"selected {len(selected)}."
        )

    # Stable ordering in the frozen dataset.
    selected.sort(
        key=lambda row: row["_source_index"]
    )

    # -------------------------------------------------------------
    # Convert to our experiment format.
    # -------------------------------------------------------------

    frozen = []

    for row in selected:
        source_index = row["_source_index"]

        frozen.append(
            {
                "id": f"folio-val-{source_index:03d}",
                "source_dataset": "benlipkin/folio",
                "source_split": "validation",
                "source_index": source_index,

                "premises": row["premises"],
                "conclusion": row["conclusion"],

                # Rename the awkward HuggingFace keys
                # for easier Python access later.
                "premises_fol": row["premises-FOL"],
                "conclusion_fol": row["conclusion-FOL"],

                "label": row["label"],

                "num_premises": len(row["premises"]),
                "is_hard": (
                    len(row["premises"])
                    >= HARD_PREMISE_THRESHOLD
                ),
            }
        )

    write_jsonl(OUTPUT_PATH, frozen)

    # -------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------

    selected_distribution = Counter(
        row["label"]
        for row in frozen
    )

    number_hard = sum(
        row["is_hard"]
        for row in frozen
    )

    file_hash = sha256(OUTPUT_PATH)

    metadata = {
        "source_dataset": "benlipkin/folio",
        "source_split": "validation",
        "source_size": len(dataset),
        "benchmark_size": len(frozen),
        "random_seed": SEED,
        "label_quotas": LABEL_QUOTAS,
        "hard_premise_threshold": HARD_PREMISE_THRESHOLD,
        "minimum_hard_examples": MIN_HARD_EXAMPLES,
        "actual_hard_examples": number_hard,
        "label_distribution": dict(selected_distribution),
        "sha256": file_hash,
    }

    with METADATA_PATH.open("w", encoding="utf-8") as f:
        json.dump(
            metadata,
            f,
            indent=2,
            ensure_ascii=False,
        )

    # -------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------

    print("\nFOLIO-50 created successfully.")
    print(f"Dataset: {OUTPUT_PATH}")
    print(f"Metadata: {METADATA_PATH}")

    print("\nLabel distribution:")
    for label in LABEL_QUOTAS:
        print(
            f"  {label}: "
            f"{selected_distribution[label]}"
        )

    print(
        f"\nExamples with >= {HARD_PREMISE_THRESHOLD} premises: "
        f"{number_hard}"
    )

    print(f"\nSHA-256:")
    print(file_hash)


if __name__ == "__main__":
    main()