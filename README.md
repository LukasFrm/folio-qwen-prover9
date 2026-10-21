# Qwen3-8B + FOLIO + Prover9 experiment

This repository contains the reproducible experiment used for the VU MIF
*Intelektualios sistemos* report. It evaluates the local `qwen3:8b` model on a
deterministic 50-example subset of the curated FOLIO validation set and verifies
every argument with Prover9 and Mace4.

## What is versioned

- `src/` — dataset builder, Qwen runner, theorem-prover runner, and evaluation.
- `data/FOLIO_instances.jsonl` — pinned curated source data.
- `data/folio50.jsonl` — deterministic experimental subset (seed 42).
- `prompts/qwen.txt` — exact model prompt.
- `prover9_inputs/` — exact first-order-logic problems sent to Prover9/Mace4.
- `prover9_outputs/` — raw proof and countermodel certificates used for the
  report appendix.
- `results/` — machine-readable model, prover, and evaluation results.

Generated submission PDFs/DOCX files and document-rendering artefacts are not
versioned. They can change with the office/LaTeX renderer and are not primary
experimental evidence.

## Prerequisites

- Python 3.11 or newer;
- [Ollama](https://ollama.com/) with the `qwen3:8b` model;
- Prover9 and Mace4 available on `PATH`.

On macOS, Prover9 can be installed with Homebrew:

```bash
brew install prover9
ollama pull qwen3:8b
```

Verify the external tools:

```bash
ollama list
prover9 -help | head
mace4 -help | head
```

## Python environment

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

## Reproduce the experiment

Run the four stages in order:

```bash
.venv/bin/python src/build_folio50.py
.venv/bin/python src/qwen_runner.py
.venv/bin/python src/prover9_runner.py
.venv/bin/python src/evaluate.py
```

The runners save progress after every example and resume completed work. A quick
smoke test can be performed before the full run:

```bash
.venv/bin/python src/qwen_runner.py --limit 1
.venv/bin/python src/prover9_runner.py --limit 1
```

The deterministic dataset builder must report:

```text
Created 50 examples
Classes: TRUE=17, FALSE=17, UNCERTAIN=16
Premises: min=2, max=8, mean=5.14, median=5, >=5=35
Ambiguous selected: 0
SHA-256: 255009ee7a62a3ad41b21ffb631e9a34d4dc4c3aa2f9748bcd25c3685fd1e5d7
```

## Main outputs

- `results/qwen3_8b_folio50.jsonl` — Qwen answers and timings;
- `results/prover9_folio50.jsonl` — formal verification summary;
- `results/final_results.csv` — joined report-ready table;
- `results/evaluation_summary.json` — aggregate metrics;
- `results/report_cases_lt.md` — Lithuanian case-analysis material;
- `prover9_outputs/` — complete raw proofs and countermodels.

`prover9_outputs/` is deliberately retained. Although it can be regenerated, it
is compact and serves as the auditable evidence behind the automatic-proof
appendix. Temporary report builds belong in `reports/`, `artifacts/`, `outputs/`,
or `rendered*/`, which are ignored by the user's global Git excludes file.
