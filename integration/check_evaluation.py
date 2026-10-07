"""Fail a release gate on incomplete or failed real-provider evidence."""

import argparse
import json
from pathlib import Path

from backend import generation, llmops


def failures(report, semantic_cases=9, clarification_cases=3):
    cases = report.get("cases", [])
    semantic = [c for c in cases if "semantic_accuracy" in c]
    clarification = [c for c in cases if "correct_clarification" in c]
    errors = []
    if len(semantic) != semantic_cases or len(clarification) != clarification_cases:
        errors.append("Evaluation is incomplete or has unexpected case counts.")
    if any(
        c.get("semantic_accuracy") is not True or c.get("execution_success") is not True
        for c in semantic
    ):
        errors.append("Semantic or execution regression.")
    if any(
        c.get("correct_clarification") is not True or c.get("query")
        for c in clarification
    ):
        errors.append("Clarification regression.")
    if report.get("prompt_revision") != llmops.prompt_revision(generation.SYSTEM):
        errors.append("Report does not match the current system prompt.")
    if report.get("workflow_version") != llmops.WORKFLOW_VERSION:
        errors.append("Report does not match the current workflow.")
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--expected-semantic-cases", type=int, default=9)
    parser.add_argument("--expected-clarification-cases", type=int, default=3)
    args = parser.parse_args()
    if min(args.expected_semantic_cases, args.expected_clarification_cases) < 1:
        parser.error("Expected case counts must be positive.")
    errors = failures(
        json.loads(args.report.read_text()),
        args.expected_semantic_cases,
        args.expected_clarification_cases,
    )
    for error in errors:
        print(error)
    if errors:
        raise SystemExit(1)
    print("Real-provider evaluation gate passed for the supplied report.")


if __name__ == "__main__":
    main()
