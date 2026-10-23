#!/usr/bin/env python3
"""Verify the curated FOLIO-50 examples with Prover9 and Mace4."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias


ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = ROOT / "data" / "folio50.jsonl"
RESULTS_PATH = ROOT / "results" / "prover9_folio50.jsonl"
INPUT_DIR = ROOT / "prover9_inputs"
OUTPUT_DIR = ROOT / "prover9_outputs"

DEFAULT_TIMEOUT_SECONDS = 5
DEFAULT_MAX_DOMAIN = 8


class FormulaError(ValueError):
    """Raised when a curated FOL formula cannot be parsed."""


@dataclass(frozen=True)
class Term:
    name: str
    arguments: tuple["Term", ...] = ()


@dataclass(frozen=True)
class Atom:
    predicate: str
    arguments: tuple[Term, ...]


@dataclass(frozen=True)
class Equality:
    left: Term
    right: Term
    negated: bool = False


@dataclass(frozen=True)
class Not:
    operand: "Formula"


@dataclass(frozen=True)
class Binary:
    operator: str
    left: "Formula"
    right: "Formula"


@dataclass(frozen=True)
class Quantifier:
    kind: str
    variable: str
    body: "Formula"


Formula: TypeAlias = Atom | Equality | Not | Binary | Quantifier


TOKEN_RE = re.compile(
    r"\s*(?:(?P<operator>[∀∃¬∧∨⊕→↔=≠(),])|"
    r"(?P<identifier>[A-Za-z_][A-Za-z0-9_]*))"
)


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    position = 0
    while position < len(text):
        match = TOKEN_RE.match(text, position)
        if match is None:
            if text[position:].strip() == "":
                break
            raise FormulaError(
                f"Unexpected character at offset {position}: {text[position:position + 20]!r}"
            )
        tokens.append(match.group("operator") or match.group("identifier"))
        position = match.end()
    return tokens


class Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.tokens = tokenize(text)
        self.position = 0

    def parse(self) -> Formula:
        formula = self.parse_biconditional()
        if self.position != len(self.tokens):
            raise FormulaError(
                f"Unexpected token {self.peek()!r} at token {self.position} in {self.text!r}"
            )
        return formula

    def parse_biconditional(self) -> Formula:
        formula = self.parse_implication()
        while self.accept("↔"):
            formula = Binary("iff", formula, self.parse_implication())
        return formula

    def peek(self) -> str | None:
        if self.position >= len(self.tokens):
            return None
        return self.tokens[self.position]

    def accept(self, token: str) -> bool:
        if self.peek() == token:
            self.position += 1
            return True
        return False

    def expect(self, token: str) -> None:
        if not self.accept(token):
            raise FormulaError(
                f"Expected {token!r}, found {self.peek()!r} in {self.text!r}"
            )

    def take_identifier(self) -> str:
        token = self.peek()
        if token is None or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
            raise FormulaError(
                f"Expected identifier, found {token!r} in {self.text!r}"
            )
        self.position += 1
        return token

    def parse_implication(self) -> Formula:
        left = self.parse_xor()
        if self.accept("→"):
            return Binary("implies", left, self.parse_implication())
        return left

    def parse_xor(self) -> Formula:
        formula = self.parse_or()
        while self.accept("⊕"):
            formula = Binary("xor", formula, self.parse_or())
        return formula

    def parse_or(self) -> Formula:
        formula = self.parse_and()
        while self.accept("∨"):
            formula = Binary("or", formula, self.parse_and())
        return formula

    def parse_and(self) -> Formula:
        formula = self.parse_unary()
        while self.accept("∧"):
            formula = Binary("and", formula, self.parse_unary())
        return formula

    def parse_unary(self) -> Formula:
        if self.accept("¬"):
            return Not(self.parse_unary())

        token = self.peek()
        if token in ("∀", "∃"):
            self.position += 1
            variable = self.take_identifier()
            kind = "all" if token == "∀" else "exists"
            return Quantifier(kind, variable, self.parse_unary())

        if self.accept("("):
            formula = self.parse_biconditional()
            self.expect(")")
            return formula

        return self.parse_atom()

    def parse_atom(self) -> Formula:
        left = self.parse_term()
        if self.accept("="):
            return Equality(left, self.parse_term())
        if self.accept("≠"):
            return Equality(left, self.parse_term(), negated=True)
        return Atom(left.name, left.arguments)

    def parse_term(self) -> Term:
        name = self.take_identifier()
        arguments: list[Term] = []
        if self.accept("("):
            if not self.accept(")"):
                while True:
                    arguments.append(self.parse_term())
                    if self.accept(")"):
                        break
                    self.expect(",")
        return Term(name, tuple(arguments))


def parse_formula(text: str) -> Formula:
    return Parser(text).parse()


def safe_symbol(name: str, prefix: str) -> str:
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    snake = re.sub(r"[^a-z0-9_]", "_", snake)
    return f"{prefix}_{snake}"


def render_term(term: Term, bound_variables: dict[str, str]) -> str:
    if not term.arguments and term.name in bound_variables:
        return bound_variables[term.name]
    if term.arguments:
        arguments = ", ".join(
            render_term(argument, bound_variables) for argument in term.arguments
        )
        return f"{safe_symbol(term.name, 'f')}({arguments})"
    return safe_symbol(term.name, "c")


def render_formula(
    formula: Formula, bound_variables: dict[str, str] | None = None
) -> str:
    bound = {} if bound_variables is None else bound_variables

    if isinstance(formula, Atom):
        arguments = ", ".join(render_term(term, bound) for term in formula.arguments)
        predicate = safe_symbol(formula.predicate, "p")
        return f"{predicate}({arguments})" if formula.arguments else predicate

    if isinstance(formula, Equality):
        equality = f"{render_term(formula.left, bound)} = {render_term(formula.right, bound)}"
        return f"-({equality})" if formula.negated else f"({equality})"

    if isinstance(formula, Not):
        return f"-({render_formula(formula.operand, bound)})"

    if isinstance(formula, Binary):
        left = render_formula(formula.left, bound)
        right = render_formula(formula.right, bound)
        if formula.operator == "and":
            return f"({left} & {right})"
        if formula.operator == "or":
            return f"({left} | {right})"
        if formula.operator == "implies":
            return f"({left} -> {right})"
        if formula.operator == "iff":
            return f"({left} <-> {right})"
        if formula.operator == "xor":
            return f"(({left} | {right}) & -({left} & {right}))"
        raise FormulaError(f"Unknown binary operator: {formula.operator}")

    if isinstance(formula, Quantifier):
        variable = f"v_{formula.variable.lower()}"
        nested_bound = dict(bound)
        nested_bound[formula.variable] = variable
        body = render_formula(formula.body, nested_bound)
        return f"{formula.kind} {variable} ({body})"

    raise TypeError(f"Unexpected formula node: {formula!r}")


def collect_constants(
    formula: Formula, bound_variables: frozenset[str] = frozenset()
) -> set[str]:
    constants: set[str] = set()

    def from_term(term: Term) -> None:
        if term.arguments:
            for argument in term.arguments:
                from_term(argument)
        elif term.name not in bound_variables:
            constants.add(term.name)

    if isinstance(formula, Atom):
        for term in formula.arguments:
            from_term(term)
    elif isinstance(formula, Equality):
        from_term(formula.left)
        from_term(formula.right)
    elif isinstance(formula, Not):
        constants.update(collect_constants(formula.operand, bound_variables))
    elif isinstance(formula, Binary):
        constants.update(collect_constants(formula.left, bound_variables))
        constants.update(collect_constants(formula.right, bound_variables))
    elif isinstance(formula, Quantifier):
        constants.update(
            collect_constants(formula.body, bound_variables | {formula.variable})
        )
    return constants


def ground_equalities(
    formula: Formula, bound_variables: frozenset[str] = frozenset()
) -> list[tuple[str, str]]:
    equalities: list[tuple[str, str]] = []
    if isinstance(formula, Equality):
        if (
            not formula.negated
            and not formula.left.arguments
            and not formula.right.arguments
            and formula.left.name not in bound_variables
            and formula.right.name not in bound_variables
        ):
            equalities.append((formula.left.name, formula.right.name))
    elif isinstance(formula, Not):
        # Equality under negation is not an alias.
        pass
    elif isinstance(formula, Binary):
        equalities.extend(ground_equalities(formula.left, bound_variables))
        equalities.extend(ground_equalities(formula.right, bound_variables))
    elif isinstance(formula, Quantifier):
        equalities.extend(
            ground_equalities(formula.body, bound_variables | {formula.variable})
        )
    return equalities


def constant_class_representatives(
    assumptions: Formula, goal: Formula
) -> list[str]:
    constants = collect_constants(assumptions) | collect_constants(goal)
    parent = {name: name for name in constants}

    def find(name: str) -> str:
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left, right in ground_equalities(assumptions):
        union(left, right)

    return sorted({find(name) for name in constants})


def unique_name_axioms(assumptions: Formula, goal: Formula) -> list[str]:
    representatives = constant_class_representatives(assumptions, goal)
    axioms: list[str] = []
    for index, left in enumerate(representatives):
        for right in representatives[index + 1 :]:
            left_term = render_term(Term(left), {})
            right_term = render_term(Term(right), {})
            axioms.append(f"-({left_term} = {right_term})")
    return axioms


def render_problem(
    assumptions: Formula, goal: Formula, use_unique_names: bool = True
) -> str:
    extra_axioms = unique_name_axioms(assumptions, goal) if use_unique_names else []
    assumptions_text = [render_formula(assumptions), *extra_axioms]
    return (
        "formulas(assumptions).\n"
        + "\n".join(f"{formula}." for formula in assumptions_text)
        + "\n"
        "end_of_list.\n\n"
        "formulas(goals).\n"
        f"{render_formula(goal)}.\n"
        "end_of_list.\n"
    )


def run_command(
    command: list[str], problem: str, timeout_seconds: int
) -> tuple[int | None, str, float, bool]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            input=problem,
            text=True,
            capture_output=True,
            timeout=timeout_seconds + 2,
            check=False,
        )
        elapsed = time.perf_counter() - started
        return completed.returncode, completed.stdout + completed.stderr, elapsed, False
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - started
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return None, stdout + stderr, elapsed, True


def prover9_status(output: str, timed_out: bool) -> str:
    if "THEOREM PROVED" in output or re.search(r"% Proof \d+ at", output):
        return "proof_found"
    if timed_out or "MAX_SECONDS" in output:
        return "timeout"
    return "no_proof"


def mace4_status(output: str, timed_out: bool) -> str:
    if "Exiting with 1 model" in output or "============================== MODEL" in output:
        return "model_found"
    if timed_out or "MAX_SECONDS" in output:
        return "timeout"
    return "no_model"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run_side(
    example_id: str,
    side: str,
    problem: str,
    timeout_seconds: int,
    max_domain: int,
) -> dict:
    input_path = INPUT_DIR / f"{example_id}_{side}.in"
    prover_output_path = OUTPUT_DIR / f"{example_id}_{side}_prover9.txt"
    mace_output_path = OUTPUT_DIR / f"{example_id}_{side}_mace4.txt"
    write_text(input_path, problem)

    return_code, output, elapsed, timed_out = run_command(
        ["prover9", "-t", str(timeout_seconds)], problem, timeout_seconds
    )
    write_text(prover_output_path, output)
    proof_status = prover9_status(output, timed_out)

    result = {
        "prover9_status": proof_status,
        "prover9_return_code": return_code,
        "prover9_seconds": round(elapsed, 4),
        "input_file": str(input_path.relative_to(ROOT)),
        "prover9_output_file": str(prover_output_path.relative_to(ROOT)),
        "mace4_status": "not_run",
        "mace4_return_code": None,
        "mace4_seconds": None,
        "mace4_output_file": None,
    }

    if proof_status != "proof_found":
        mace_code, mace_output, mace_elapsed, mace_timed_out = run_command(
            [
                "mace4",
                "-t",
                str(timeout_seconds),
                "-n",
                "2",
                "-N",
                str(max_domain),
            ],
            problem,
            timeout_seconds,
        )
        write_text(mace_output_path, mace_output)
        result.update(
            {
                "mace4_status": mace4_status(mace_output, mace_timed_out),
                "mace4_return_code": mace_code,
                "mace4_seconds": round(mace_elapsed, 4),
                "mace4_output_file": str(mace_output_path.relative_to(ROOT)),
            }
        )

    return result


def classify(positive: dict, negative: dict) -> tuple[str, bool, bool]:
    positive_proof = positive["prover9_status"] == "proof_found"
    negative_proof = negative["prover9_status"] == "proof_found"

    if positive_proof and negative_proof:
        # FOLIO resolves labels by checking positive entailment first. Retain
        # that label while explicitly recording that the premises explode.
        return "True", True, True
    if positive_proof:
        return "True", True, False
    if negative_proof:
        return "False", True, False

    both_countermodels = (
        positive["mace4_status"] == "model_found"
        and negative["mace4_status"] == "model_found"
    )
    if both_countermodels:
        return "Uncertain", True, False
    return "Unverified", False, False


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as destination:
        destination.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def clear_primary_artifacts() -> None:
    """Remove generated artifacts for the current folio50 experiment."""
    for directory, pattern in (
        (INPUT_DIR, "folio50-*.in"),
        (OUTPUT_DIR, "folio50-*.txt"),
    ):
        if directory.exists():
            for path in directory.glob(pattern):
                path.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="Process at most N pending examples.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Seconds per Prover9/Mace4 call (default: {DEFAULT_TIMEOUT_SECONDS}).",
    )
    parser.add_argument(
        "--max-domain",
        type=int,
        default=DEFAULT_MAX_DOMAIN,
        help=f"Largest Mace4 domain (default: {DEFAULT_MAX_DOMAIN}).",
    )
    parser.add_argument(
        "--no-unique-names",
        action="store_true",
        help="Disable distinct-name axioms for constants.",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Start a fresh run by replacing the current primary results file.",
    )
    return parser.parse_args()


def validate_translation(dataset: list[dict]) -> None:
    for example in dataset:
        parse_formula(example["premises_fol_combined"])
        parse_formula(example["conclusion_fol"])


def main() -> None:
    args = parse_args()
    if shutil.which("prover9") is None or shutil.which("mace4") is None:
        raise RuntimeError("Both prover9 and mace4 must be installed and available on PATH.")

    dataset = load_jsonl(DATASET_PATH)
    if len(dataset) != 50:
        raise RuntimeError(f"Expected 50 examples, found {len(dataset)}.")
    validate_translation(dataset)

    dataset_hash = sha256(DATASET_PATH)
    if args.restart:
        if RESULTS_PATH.exists():
            RESULTS_PATH.unlink()
        clear_primary_artifacts()

    existing = load_jsonl(RESULTS_PATH) if RESULTS_PATH.exists() else []
    stale = [
        row["id"]
        for row in existing
        if row.get("dataset_sha256") != dataset_hash
    ]
    if stale:
        raise RuntimeError(
            "Existing results belong to a different dataset. "
            "Use --restart after preserving them; mismatched IDs: "
            + ", ".join(stale[:5])
        )
    completed_ids = {row["id"] for row in existing}
    processed = 0
    print(f"Dataset: {len(dataset)} examples")
    print(f"Completed previously: {len(completed_ids)}")

    for index, example in enumerate(dataset, start=1):
        if example["id"] in completed_ids:
            print(f"[{index}/50] {example['id']} — already completed")
            continue
        if args.limit is not None and processed >= args.limit:
            break

        assumptions = parse_formula(example["premises_fol_combined"])
        conclusion = parse_formula(example["conclusion_fol"])
        use_unique_names = not args.no_unique_names
        minimum_domain = (
            len(constant_class_representatives(assumptions, conclusion))
            if use_unique_names
            else 2
        )
        effective_max_domain = max(args.max_domain, minimum_domain)
        positive_problem = render_problem(assumptions, conclusion, use_unique_names)
        negative_problem = render_problem(assumptions, Not(conclusion), use_unique_names)

        print(f"[{index}/50] {example['id']} (gold={example['label']})")
        positive = run_side(
            example["id"], "conclusion", positive_problem, args.timeout, effective_max_domain
        )
        negative = run_side(
            example["id"], "negated_conclusion", negative_problem, args.timeout, effective_max_domain
        )
        classification, fully_verified, premises_inconsistent = classify(
            positive, negative
        )
        matches_gold = classification == example["label"]

        result = {
            "id": example["id"],
            "source_story_id": example["source_story_id"],
            "source_example_id": example["source_example_id"],
            "dataset_sha256": dataset_hash,
            "gold_label": example["label"],
            "prover9_label": classification,
            "matches_gold": matches_gold,
            "fully_verified": fully_verified,
            "premises_inconsistent": premises_inconsistent,
            "unique_names": use_unique_names,
            "positive": positive,
            "negative": negative,
            "timeout_seconds": args.timeout,
            "max_mace4_domain": effective_max_domain,
            "minimum_unique_name_domain": minimum_domain,
        }
        append_jsonl(RESULTS_PATH, result)
        processed += 1

        marker = "✓" if matches_gold and fully_verified else "!"
        print(
            f"    {marker} classified={classification}; "
            f"positive={positive['prover9_status']}/{positive['mace4_status']}; "
            f"negative={negative['prover9_status']}/{negative['mace4_status']}"
        )

    results = load_jsonl(RESULTS_PATH) if RESULTS_PATH.exists() else []
    verified = sum(row["fully_verified"] for row in results)
    matching = sum(row["matches_gold"] for row in results)
    print()
    print(f"Completed: {len(results)}/50")
    print(f"Fully verified: {verified}/{len(results)}" if results else "Fully verified: 0")
    print(f"Matches gold: {matching}/{len(results)}" if results else "Matches gold: 0")
    print(f"Results: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
