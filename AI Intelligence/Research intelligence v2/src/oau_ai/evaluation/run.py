"""CLI entry point for RAGAS evaluation.

Usage:
    python -m oau_ai.evaluation.run --max-examples 50 --metrics faithfulness,answer_relevancy
    python -m oau_ai.evaluation.run --dataset-csv /path/to/theses.csv --output results.json
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .dataset import EvaluationDataset, load_dataset_from_csv
from .evaluator import RagasEvaluator
from .metrics import available_metrics


def main(argv: Optional[list[str]] = None) -> int:
    """Run the RAGAS evaluation from the command line.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    parser = argparse.ArgumentParser(
        description="Run RAGAS evaluation for Phase 3 V2 RAG quality."
    )
    parser.add_argument(
        "--dataset-csv",
        default=None,
        help="Path to theses CSV (default: bundled Oxford theses CSV).",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=None,
        help="Maximum number of examples to evaluate.",
    )
    parser.add_argument(
        "--metrics",
        default=None,
        help=(
            "Comma-separated metric names (default: all available). "
            f"Available: {available_metrics()}"
        ),
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file for results JSON (default: stdout).",
    )
    parser.add_argument(
        "--model-provider",
        default="deepseek",
        help="LLM provider name for run metadata (default: deepseek).",
    )
    parser.add_argument(
        "--model-model",
        default="deepseek-chat",
        help="Model name for run metadata (default: deepseek-chat).",
    )

    args = parser.parse_args(argv)

    # Load dataset.
    dataset = load_dataset_from_csv(
        csv_path=args.dataset_csv,
        max_examples=args.max_examples,
    )

    if dataset.total_examples == 0:
        print("Error: No examples loaded from dataset.", file=sys.stderr)
        return 1

    # Parse metrics.
    metrics = None
    if args.metrics:
        metrics = [m.strip() for m in args.metrics.split(",") if m.strip()]

    # Run evaluation.
    evaluator = RagasEvaluator(
        model_provider=args.model_provider,
        model_model=args.model_model,
    )
    run = evaluator.evaluate(dataset, metrics=metrics)

    # Output results.
    output = json.dumps(run.to_dict(), indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
            f.write("\n")
        print(f"Results written to {args.output}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
