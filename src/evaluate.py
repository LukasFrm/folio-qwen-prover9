#!/usr/bin/env python3
"""Combine Qwen and Prover9 results into report-ready evaluation artifacts."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = ROOT / "data" / "folio50.jsonl"
QWEN_PATH = ROOT / "results" / "qwen3_8b_folio50.jsonl"
PROVER_PATH = ROOT / "results" / "prover9_folio50.jsonl"
CSV_PATH = ROOT / "results" / "final_results.csv"
SUMMARY_PATH = ROOT / "results" / "evaluation_summary.json"
CASES_PATH = ROOT / "results" / "report_cases_lt.md"

LABELS = ("True", "False", "Uncertain")

REPORT_CASES = (
    {
        "id": "folio50-001",
        "title": "Teisingai nustatyta, kad išvada seka",
        "analysis": (
            "Iš prielaidų gauname, kad „The Legend of Zelda“ yra žaidimas ir kad "
            "jo parduota daugiau nei vienas milijonas kopijų. Universalioji taisyklė "
            "teigia, kad kiekvienas žaidimas, kurio parduota daugiau nei vienas "
            "milijonas kopijų, patenka į Top 10 sąrašą. Pritaikius modus ponens "
            "tiesiogiai gaunama išvada `InTop10(theLegendofZelda)`. Qwen ir Prover9 "
            "sutapo su etalonine žyma `True`."
        ),
    },
    {
        "id": "folio50-002",
        "title": "Teisingai nustatyta, kad išvada neseka",
        "analysis": (
            "Visos prielaidos aprašo „The Legend of Zelda“; nė viena prielaida "
            "nemini FIFA 22 ir nenustato jo kūrėjo. Todėl negalima įrodyti nei "
            "egzistencinės išvados apie japonų bendrovę, sukūrusią FIFA 22, nei jos "
            "neiginio. Mace4 rado po baigtinį kontrmodelį abiem kryptims, todėl "
            "`Uncertain` yra pagrįsta žyma. Qwen šį neapibrėžtumą atpažino teisingai."
        ),
    },
    {
        "id": "folio50-024",
        "title": "Klaida: išvada turėjo sekti, bet Qwen pasirinko „Uncertain“",
        "analysis": (
            "Šeštoji formalizuota prielaida yra XOR neiginys: Luke gimimas daugiavaisiame "
            "gimdyme ir gyvenimas su nepažįstamaisiais turi vienodą teisingumo reikšmę. "
            "Tarkime, kad `BornIn(luke, multipleBirth)` teisinga. Tuomet pagal 1 ir 5 "
            "prielaidas Luke leidžia laiką su broliais ar seserimis ir gyvena namuose; "
            "pagal 4 prielaidą jis negyvena su nepažįstamaisiais. Tačiau XOR neiginys "
            "iš teisingo `BornIn` reikalauja teisingo `LiveWith`, todėl gaunamas "
            "prieštaravimas. Vadinasi, `BornIn` yra klaidinga. Jei Luke dažnai skųstųsi "
            "broliais ar seserimis, 3 ir 2 prielaidos vėl leistų išvesti `BornIn`; todėl "
            "klaidingas ir `ComplainAboutOften`. Prover9 įrodė visą konjunkcinę išvadą. "
            "Qwen klaidos vieta – nepakankamai išnaudotas XOR neiginys ir netiesioginis "
            "įrodymas prieštaravimu."
        ),
    },
    {
        "id": "folio50-007",
        "title": "Klaida: išvada neturėjo sekti, bet Qwen pasirinko „True“",
        "analysis": (
            "Taisyklės antecedentas yra konjunkcija: vasara yra mėgstamiausias sezonas "
            "tik tiems asmenims, kurie ir yra studentai, ir nori ilgų atostogų. Apie "
            "Jamesą žinoma tik antroji sąlyga – `Want(james, longVacation)`; prielaidos "
            "`Student(james)` nėra. Todėl modus ponens taikyti negalima. Mace4 rado "
            "modelį, kuriame Jameso mėgstamiausias sezonas yra vasara, ir modelį, "
            "kuriame taip nėra. Qwen klaida atitinka antecedento dalies praleidimą: "
            "noras turėti ilgas atostogas buvo traktuotas kaip pakankama, nors taisyklėje "
            "jis yra tik viena iš dviejų būtinų sąlygų."
        ),
    },
)


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def indexed(rows: list[dict], name: str) -> dict[str, dict]:
    result = {row["id"]: row for row in rows}
    if len(result) != len(rows):
        raise RuntimeError(f"Duplicate IDs in {name}.")
    return result


def validate_inputs(
    dataset: dict[str, dict], qwen: dict[str, dict], prover: dict[str, dict]
) -> None:
    if len(dataset) != 50:
        raise RuntimeError(f"Expected 50 dataset rows, found {len(dataset)}.")
    if set(dataset) != set(qwen):
        raise RuntimeError("Qwen result IDs do not exactly match the dataset.")
    if set(dataset) != set(prover):
        raise RuntimeError("Prover9 result IDs do not exactly match the dataset.")
    if not all(row["fully_verified"] for row in prover.values()):
        raise RuntimeError("At least one Prover9 result is not fully verified.")
    if not all(row["matches_gold"] for row in prover.values()):
        raise RuntimeError("At least one Prover9 label disagrees with the gold label.")


def build_combined_rows(
    dataset: dict[str, dict], qwen: dict[str, dict], prover: dict[str, dict]
) -> list[dict]:
    rows: list[dict] = []
    for example_id in sorted(dataset, key=lambda value: int(value.rsplit("-", 1)[1])):
        source = dataset[example_id]
        model = qwen[example_id]
        proof = prover[example_id]
        rows.append(
            {
                "id": example_id,
                "source_story_id": source["source_story_id"],
                "source_example_id": source["source_example_id"],
                "premise_count": source["premise_count"],
                "has_at_least_5_premises": source["has_at_least_5_premises"],
                "gold_label": source["label"],
                "qwen_label": model["predicted_label"],
                "qwen_correct": model["correct"],
                "qwen_duration_seconds": model["duration_seconds"],
                "prover9_label": proof["prover9_label"],
                "prover9_fully_verified": proof["fully_verified"],
                "premises_inconsistent": proof["premises_inconsistent"],
                "positive_proof": proof["positive"]["prover9_status"]
                == "proof_found",
                "negative_proof": proof["negative"]["prover9_status"]
                == "proof_found",
                "positive_countermodel": proof["positive"]["mace4_status"]
                == "model_found",
                "negative_countermodel": proof["negative"]["mace4_status"]
                == "model_found",
            }
        )
    return rows


def write_csv(rows: list[dict]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build_summary(rows: list[dict]) -> dict:
    total = len(rows)
    correct = sum(row["qwen_correct"] for row in rows)
    confusion = Counter((row["gold_label"], row["qwen_label"]) for row in rows)

    per_class = {}
    for label in LABELS:
        class_rows = [row for row in rows if row["gold_label"] == label]
        class_correct = sum(row["qwen_correct"] for row in class_rows)
        per_class[label] = {
            "total": len(class_rows),
            "correct": class_correct,
            "accuracy": class_correct / len(class_rows),
        }

    by_premise_count = {}
    for group, predicate in (
        ("2_to_4", lambda count: count < 5),
        ("5_or_more", lambda count: count >= 5),
    ):
        group_rows = [row for row in rows if predicate(row["premise_count"])]
        group_correct = sum(row["qwen_correct"] for row in group_rows)
        by_premise_count[group] = {
            "total": len(group_rows),
            "correct": group_correct,
            "accuracy": group_correct / len(group_rows),
        }

    return {
        "examples": total,
        "qwen_correct": correct,
        "qwen_accuracy": correct / total,
        "average_duration_seconds": sum(
            row["qwen_duration_seconds"] for row in rows
        )
        / total,
        "per_class": per_class,
        "confusion_matrix": {
            gold: {predicted: confusion[(gold, predicted)] for predicted in LABELS}
            for gold in LABELS
        },
        "by_premise_count": by_premise_count,
        "prover9_fully_verified": sum(row["prover9_fully_verified"] for row in rows),
        "prover9_matches_gold": sum(
            row["prover9_label"] == row["gold_label"] for row in rows
        ),
        "inconsistent_premise_sets": [
            row["id"] for row in rows if row["premises_inconsistent"]
        ],
        "qwen_error_ids": [row["id"] for row in rows if not row["qwen_correct"]],
        "report_case_ids": [case["id"] for case in REPORT_CASES],
    }


def write_summary(summary: dict) -> None:
    SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def format_case(case: dict, source: dict, model: dict, proof: dict) -> str:
    premises = "\n".join(
        f"{number}. {premise}" for number, premise in enumerate(source["premises"], 1)
    )
    evidence = []
    for side in ("positive", "negative"):
        for key in ("prover9_output_file", "mace4_output_file"):
            value = proof[side].get(key)
            if value:
                evidence.append(f"`{value}`")

    return f"""## {case['title']}

**Atvejis:** `{source['id']}` / `{source['source_example_id']}`  
**Etalonas:** `{source['label']}`  
**Qwen3-8B:** `{model['predicted_label']}`  
**Prover9/Mace4:** `{proof['prover9_label']}`

### Prielaidos

{premises}

### Išvada

{source['conclusion']}

### FOL išvada

```text
{source['conclusion_fol']}
```

### Analizė

{case['analysis']}

### Automatinio tikrinimo failai

{', '.join(evidence)}
"""


def write_cases(
    dataset: dict[str, dict], qwen: dict[str, dict], prover: dict[str, dict]
) -> None:
    sections = [
        "# Keturi ataskaitos atvejai",
        (
            "Pastaba: pagrindiniame eksperimente Qwen išsaugojo tik struktūrinę "
            "klasės žymą, todėl klaidų analizė yra išorinė loginė analizė, paremta "
            "prielaidomis, Prover9 įrodymais ir Mace4 kontrmodeliais; ji nėra "
            "pateikiama kaip modelio paslėpta samprotavimo eiga."
        ),
    ]
    for case in REPORT_CASES:
        example_id = case["id"]
        sections.append(
            format_case(case, dataset[example_id], qwen[example_id], prover[example_id])
        )
    CASES_PATH.write_text("\n\n".join(sections).strip() + "\n", encoding="utf-8")


def main() -> None:
    dataset = indexed(read_jsonl(DATASET_PATH), "dataset")
    qwen = indexed(read_jsonl(QWEN_PATH), "Qwen results")
    prover = indexed(read_jsonl(PROVER_PATH), "Prover9 results")
    validate_inputs(dataset, qwen, prover)

    combined = build_combined_rows(dataset, qwen, prover)
    summary = build_summary(combined)
    write_csv(combined)
    write_summary(summary)
    write_cases(dataset, qwen, prover)

    print(f"Combined rows: {len(combined)}")
    print(f"Qwen accuracy: {summary['qwen_correct']}/{summary['examples']} "
          f"({summary['qwen_accuracy']:.2%})")
    print(f"CSV: {CSV_PATH}")
    print(f"Summary: {SUMMARY_PATH}")
    print(f"Lithuanian cases: {CASES_PATH}")


if __name__ == "__main__":
    main()
