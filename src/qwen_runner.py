import argparse
import hashlib
import importlib.metadata
import json
import re
import time
from pathlib import Path
from typing import Literal

from ollama import chat, show
from pydantic import BaseModel


MODEL = "qwen3:8b"
TEMPERATURE = 0
SEED = 42
NUM_CTX = 4096
NUM_PREDICT = 32
MODEL_BLOB_RE = re.compile(r"^FROM .*/sha256-([0-9a-f]{64})$", re.MULTILINE)

ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = ROOT / "data" / "folio50.jsonl"
RESULTS_PATH = ROOT / "results" / "qwen3_8b_folio50.jsonl"


class ModelAnswer(BaseModel):
    label: Literal["True", "False"]


SYSTEM_PROMPT = """
You are solving a two-class logical reasoning problem.

You will receive a set of premises and a conclusion.

Every example has a known answer. Classify the conclusion as exactly one of:

True:
The conclusion logically follows from the premises.

False:
The negation of the conclusion logically follows from the premises.

Use only the information contained in the premises.
Do not rely on outside knowledge.

Return only the requested structured result.
""".strip()


def build_prompt(example: dict) -> str:
    premises = "\n".join(
        f"{i + 1}. {premise}"
        for i, premise in enumerate(example["premises"])
    )

    return f"""
Premises:
{premises}

Conclusion:
{example["conclusion"]}

Determine whether the conclusion is True or False.
""".strip()


def load_dataset() -> list[dict]:
    with DATASET_PATH.open(encoding="utf-8") as f:
        dataset = [json.loads(line) for line in f if line.strip()]

    if len(dataset) != 50:
        raise RuntimeError(
            f"Expected 50 examples in {DATASET_PATH}, found {len(dataset)}."
        )
    return dataset


def dataset_sha256() -> str:
    digest = hashlib.sha256()
    with DATASET_PATH.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_runtime_metadata() -> dict:
    details = show(MODEL)
    blob_match = MODEL_BLOB_RE.search(details.modelfile or "")
    return {
        "ollama_python_version": importlib.metadata.version("ollama"),
        "model_blob_sha256": blob_match.group(1) if blob_match else None,
        "model_parameter_size": details.details.parameter_size,
        "model_quantization": details.details.quantization_level,
    }


def load_existing_results() -> list[dict]:
    if not RESULTS_PATH.exists():
        return []

    with RESULTS_PATH.open(encoding="utf-8") as f:
        return [
            json.loads(line)
            for line in f
            if line.strip()
        ]


def save_result(result: dict) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    with RESULTS_PATH.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                result,
                ensure_ascii=False,
            )
            + "\n"
        )


def print_summary(results: list[dict]) -> None:
    if not results:
        return

    correct = sum(
        result["correct"]
        for result in results
    )

    total = len(results)
    accuracy = correct / total

    print()
    print("Current results")
    print("---------------")
    print(f"Completed: {total}")
    print(f"Correct:   {correct}")
    print(f"Accuracy:  {accuracy:.2%}")

    avg_time = sum(
        result["duration_seconds"]
        for result in results
    ) / total

    print(f"Avg time:  {avg_time:.2f}s")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Qwen3-8B on the deterministic two-class FOLIO-50 subset."
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Process at most this many not-yet-completed examples.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue after an Ollama/API error instead of stopping immediately.",
    )
    parser.add_argument(
        "--num-gpu",
        type=int,
        help="Override Ollama GPU layers (default: let Ollama choose).",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Start a fresh run by replacing the current primary results file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = load_dataset()
    dataset_hash = dataset_sha256()
    runtime_metadata = model_runtime_metadata()
    if args.restart and RESULTS_PATH.exists():
        RESULTS_PATH.unlink()
    existing_results = load_existing_results()

    stale = [
        result["id"]
        for result in existing_results
        if result.get("dataset_sha256") != dataset_hash
    ]
    if stale:
        raise RuntimeError(
            "Existing results belong to a different dataset. "
            "Use --restart after preserving them; mismatched IDs: "
            + ", ".join(stale[:5])
        )

    completed_ids = {
        result["id"]
        for result in existing_results
    }

    print(f"Dataset: {len(dataset)} examples")
    print(f"Dataset SHA-256: {dataset_hash}")
    print(f"Model: {MODEL}")
    print(f"Completed previously: {len(completed_ids)}")
    print()

    results = list(existing_results)
    processed_this_run = 0

    for index, example in enumerate(dataset, start=1):
        example_id = example["id"]

        if example_id in completed_ids:
            print(
                f"[{index}/{len(dataset)}] "
                f"{example_id} — already completed"
            )
            continue

        if args.limit is not None and processed_this_run >= args.limit:
            break

        print(
            f"[{index}/{len(dataset)}] "
            f"{example_id} "
            f"(gold={example['label']})"
        )

        prompt = build_prompt(example)
        options = {
            "temperature": TEMPERATURE,
            "seed": SEED,
            "num_ctx": NUM_CTX,
            "num_predict": NUM_PREDICT,
        }
        if args.num_gpu is not None:
            options["num_gpu"] = args.num_gpu

        start_time = time.perf_counter()

        try:
            response = chat(
                model=MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                think=False,
                format=ModelAnswer.model_json_schema(),
                options=options,
            )

            duration = time.perf_counter() - start_time

            parsed = ModelAnswer.model_validate_json(
                response.message.content
            )

            predicted_label = parsed.label
            correct = predicted_label == example["label"]

            result = {
                "id": example_id,
                "source_index": example["source_index"],
                "source_story_id": example["source_story_id"],
                "source_example_id": example["source_example_id"],
                "premise_count": example["premise_count"],
                "gold_label": example["label"],
                "predicted_label": predicted_label,
                "correct": correct,
                "raw_response": response.message.content,
                "prompt": prompt,
                "duration_seconds": round(duration, 4),
                "model": MODEL,
                **runtime_metadata,
                "dataset_sha256": dataset_hash,
                "temperature": TEMPERATURE,
                "seed": SEED,
                "thinking": False,
                "num_ctx": NUM_CTX,
                "num_predict": NUM_PREDICT,
                "num_gpu": args.num_gpu,
                "prompt_mode": "two_class_known_labels",
            }

            save_result(result)
            results.append(result)
            processed_this_run += 1

            status = "✓" if correct else "✗"

            print(
                f"    {status} "
                f"predicted={predicted_label} "
                f"time={duration:.2f}s"
            )

        except Exception as exc:
            duration = time.perf_counter() - start_time
            processed_this_run += 1

            print(
                f"    ERROR after {duration:.2f}s: "
                f"{type(exc).__name__}: {exc}"
            )
            if not args.continue_on_error:
                print("Stopping after the first error; no result was saved.")
                break

    print_summary(results)

    print()
    print(f"Results file:")
    print(RESULTS_PATH)


if __name__ == "__main__":
    main()
