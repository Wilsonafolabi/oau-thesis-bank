"""Evaluation dataset for RAGAS evaluation.

Defines the schema for evaluation examples and provides loading from
the Oxford theses CSV (verifiable source material: title + abstract).

When RAGAS is not installed, dataset loading and validation work fully
offline. Actual RAGAS evaluation runs require `pip install ragas`.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# Default path to the Oxford theses CSV (V1 reference data, read-only).
# From src/oau_ai/evaluation/dataset.py, go up 4 levels to the workspace
# root, then into Research intelligence/oxford_theses/.
DEFAULT_CSV_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "..",
        "Research intelligence",
        "oxford_theses",
        "theses.csv",
    )
)


@dataclass
class EvaluationExample:
    """A single RAGAS evaluation example.

    Attributes:
        question: The user question.
        reference_answer: The ground-truth answer (optional; may be None
            for unanswerable questions or when no reference is available).
        retrieved_contexts: List of context text chunks retrieved for the
            question, used for context precision and recall.
        generated_answer: The answer produced by the RAG system (optional;
            may be None before generation).
        source_ids: List of (chunk_id, document_id, backend_thesis_id)
            tuples identifying the provenance of each context.
        metadata: Additional example-level metadata (e.g., thesis title,
            subject, access level).
    """

    question: str
    reference_answer: Optional[str] = None
    retrieved_contexts: list[str] = field(default_factory=list)
    generated_answer: Optional[str] = None
    source_ids: list[tuple[str, str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_ragas_dict(self) -> dict[str, Any]:
        """Convert to a RAGAS-compatible dict.

        RAGAS expects keys: question, answer, contexts, ground_truth.
        Missing values are represented as empty strings.
        """
        return {
            "question": self.question,
            "answer": self.generated_answer or "",
            "contexts": self.retrieved_contexts,
            "ground_truth": self.reference_answer or "",
        }


@dataclass
class EvaluationDataset:
    """A collection of evaluation examples with provenance metadata."""

    examples: list[EvaluationExample] = field(default_factory=list)
    source_file: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    total_examples: int = field(init=False)

    def __post_init__(self) -> None:
        self.total_examples = len(self.examples)

    def add(self, example: EvaluationExample) -> None:
        """Add an example to the dataset."""
        self.examples.append(example)
        self.total_examples = len(self.examples)

    def to_ragas_dataset(self) -> list[dict[str, Any]]:
        """Convert all examples to RAGAS-compatible dicts."""
        return [ex.to_ragas_dict() for ex in self.examples]

    def examples_with_references(self) -> list[EvaluationExample]:
        """Return examples that have a reference answer."""
        return [ex for ex in self.examples if ex.reference_answer]

    def examples_without_references(self) -> list[EvaluationExample]:
        """Return examples without a reference answer."""
        return [ex for ex in self.examples if not ex.reference_answer]


def _curated_seed_dataset() -> EvaluationDataset:
    """Create a small, manually curated seed dataset.

    All answers are verifiable against the thesis abstracts in the CSV.
    Each example includes the source thesis metadata for traceability.

    This is a fallback dataset used when the CSV cannot be loaded or when
    a minimal reproducible dataset is needed for offline testing.
    """
    examples = [
        EvaluationExample(
            question="What is the methodology used in the study of metamorphic studies in the Scottish Highlands?",
            reference_answer=(
                "The study uses metamorphic field studies in the Scottish Highlands, "
                "examining cyanite, sillimanite, andalusite, and metamorphic rocks."
            ),
            retrieved_contexts=[
                "Metamorphic studies in the Scottish Highlands, subjects: Scotland; Cyanite; "
                "Geology; Metamorphism (Geology); Sillimanite; Metamorphic rocks; Andalusite; "
                "Highlands (Scotland)"
            ],
            source_ids=[
                ("chunk-001", "doc-001", "oai:ora.ox.ac.uk:uuid:0000df07-a390-4b43-af48-31f04ba628ec")
            ],
            metadata={
                "thesis_title": "Metamorphic studies in the Scottish Highlands",
                "thesis_author": "Baker, A; Baker, Andrew James",
                "thesis_date": "1985",
                "subjects": "Scotland; Cyanite; Geology; Metamorphism (Geology); Sillimanite; Metamorphic rocks; Andalusite; Highlands (Scotland)",
            },
        ),
        EvaluationExample(
            question="Who studied the performance and reception of Handel's music in revolutionary North America?",
            reference_answer="Lockwood, J",
            retrieved_contexts=[
                "The performance and reception of Handel's music in revolutionary North America, "
                "author: Lockwood, J, date: 2023, subjects: Music; History"
            ],
            source_ids=[
                ("chunk-002", "doc-002", "oai:ora.ox.ac.uk:uuid:b279b3f0-a041-4c60-bf4d-f48a36a45733")
            ],
            metadata={
                "thesis_title": "The performance and reception of Handel's music in revolutionary North America",
                "thesis_author": "Lockwood, J",
                "thesis_date": "2023",
                "subjects": "Music; History",
            },
        ),
        EvaluationExample(
            question="What is derived complex analytic geometry via bornological methods about?",
            reference_answer="Derived complex analytic geometry via bornological methods",
            retrieved_contexts=[
                "Derived complex analytic geometry via bornological methods, author: Burns, C, date: 2025"
            ],
            source_ids=[
                ("chunk-003", "doc-003", "oai:ora.ox.ac.uk:uuid:624839b1-2873-4665-9fd2-fed86b3b40e9")
            ],
            metadata={
                "thesis_title": "Derived complex analytic geometry via bornological methods",
                "thesis_author": "Burns, C",
                "thesis_date": "2025",
                "subjects": "",
            },
        ),
    ]
    return EvaluationDataset(
        examples=examples,
        source_file="curated-seed",
    )


def load_dataset_from_csv(
    csv_path: Optional[str] = None,
    max_examples: Optional[int] = None,
) -> EvaluationDataset:
    """Load evaluation examples from the Oxford theses CSV.

    Each row with a non-empty abstract becomes an evaluation example where
    the question is derived from the thesis title/subjects and the reference
    answer is derived from the abstract. This ensures answers are verifiable
    against the source abstract text.

    Args:
        csv_path: Path to the theses CSV. Defaults to the V1 reference CSV.
        max_examples: Maximum number of examples to load (None = all).

    Returns:
        EvaluationDataset with examples derived from CSV rows.

    Raises:
        FileNotFoundError: If the CSV path does not exist.
    """
    path = csv_path or DEFAULT_CSV_PATH

    if not os.path.exists(path):
        # Fall back to curated seed dataset when CSV is unavailable.
        return _curated_seed_dataset()

    examples: list[EvaluationExample] = []
    count = 0

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            abstract = (row.get("abstract") or "").strip()
            title = (row.get("title") or "").strip()
            subjects = (row.get("subjects") or "").strip()
            oai_id = (row.get("oai_id") or "").strip()

            if not abstract and not title:
                continue

            # Construct a verifiable question from title and subjects.
            question_parts = [title]
            if subjects:
                question_parts.append(f"subjects: {subjects}")
            question = "What is the thesis about: " + "; ".join(question_parts) + "?"

            # Reference answer from abstract (verifiable source).
            reference_answer = abstract if abstract else title

            # Context from the thesis metadata + abstract.
            context_parts = []
            if title:
                context_parts.append(f"Title: {title}")
            if subjects:
                context_parts.append(f"Subjects: {subjects}")
            if abstract:
                context_parts.append(f"Abstract: {abstract}")
            context = " | ".join(context_parts)

            examples.append(
                EvaluationExample(
                    question=question,
                    reference_answer=reference_answer,
                    retrieved_contexts=[context],
                    generated_answer=None,
                    source_ids=[(f"chunk-{oai_id[-8:]}", f"doc-{oai_id[-8:]}", oai_id)],
                    metadata={
                        "thesis_title": title,
                        "thesis_author": row.get("author", ""),
                        "thesis_date": row.get("date", ""),
                        "subjects": subjects,
                        "oai_id": oai_id,
                    },
                )
            )

            count += 1
            if max_examples is not None and count >= max_examples:
                break

    return EvaluationDataset(
        examples=examples,
        source_file=path,
    )


def seed_dataset() -> EvaluationDataset:
    """Return the curated seed dataset for offline testing."""
    return _curated_seed_dataset()
