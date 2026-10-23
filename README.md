# Qwen3-8B + FOLIO + Prover9 experiment

This repository contains the reproducible experiment used for the VU MIF
*Intelektualios sistemos* report. It evaluates the local `qwen3:8b` model on a
deterministic two-class, 50-example subset of the curated FOLIO validation set
and verifies every argument with Prover9 and Mace4. The experiment contains 25
`True` and 25 `False` examples; `Uncertain` is not an allowed gold or predicted
label.

## What is versioned

- `src/` — dataset builder, Qwen runner, theorem-prover runner, and evaluation.
- `data/FOLIO_instances.jsonl` — pinned curated source data.
- `data/folio50.jsonl` — deterministic known-answer subset (seed 42).
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

Run the four stages in order. `--restart` replaces the current primary result
files so the experiment can be reproduced from a clean state.

```bash
.venv/bin/python src/build_folio50.py
.venv/bin/python src/qwen_runner.py --restart
.venv/bin/python src/prover9_runner.py --restart
.venv/bin/python src/evaluate.py
```

The same two-class prompt is used for all 50 examples. `True` means that the
conclusion follows; `False` means that the negation of the conclusion follows.
It does not mean merely that the conclusion cannot be proved.

The subset contains one documented ambiguity exception, `concl_452_30`, needed
for the required `False -> True` qualitative error. The source flags only the
English `either ... or` wording; its curation note says that the FOL translation
is accurate, and its original, corrected, and Z3 labels all agree on `False`.
Prover9 proves the negation of its conclusion. All other selected entries are
unambiguous.

The runners save progress after every example and resume completed work. A quick
smoke test can be performed before the full run:

```bash
.venv/bin/python src/qwen_runner.py --limit 1
.venv/bin/python src/prover9_runner.py --limit 1
```

The deterministic dataset builder must report:

```text
Created 50 examples
Classes: TRUE=25, FALSE=25
Premises: min=2, max=8, mean=5.00, median=5, >=5=34
Ambiguous selected: 1
SHA-256: c7f047155b6e9576375f6e6322825a7b338c3fe59fc3c0fb83b1b8f55fbe4004
```

The recorded run used Ollama server 0.34.0, CLI client 0.40.0, Python package
0.6.3, and model manifest digest `b3d9ba7c899c` (Q4_K_M model blob SHA-256
`a3de86cd1c132c822487ededd47a324c50491393e6565cd14bafa40d0b8e686f`). With
seed 42 and temperature 0 it produced 48/50 correct answers (96%): `True` 24/25
and `False` 24/25. Exact outputs can still vary if the Ollama runtime, model
digest, quantization, or hardware backend changes.

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
