# build_docdm_data.py
#
# DocDM-Evidence dataset builder
#
# Pipeline:
# PDFs
#   -> text extraction
#   -> document chunks
#   -> factual claims
#   -> supported / contradicted / not_mentioned candidates
#   -> LLM validation
#   -> document-level train/val/test split
#   -> JSONL outputs
#
# No model training happens in this file.

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import requests


# ============================================================
# CONFIG
# ============================================================

PDF_DIR = Path("./pdfs")
DATA_DIR = Path("./data")

RAW_OUTPUT = DATA_DIR / "docdm_evidence_raw.jsonl"
TRAIN_OUTPUT = DATA_DIR / "docdm_evidence_train.jsonl"
VAL_OUTPUT = DATA_DIR / "docdm_evidence_val.jsonl"
TEST_OUTPUT = DATA_DIR / "docdm_evidence_test.jsonl"
MANIFEST_OUTPUT = DATA_DIR / "docdm_manifest.jsonl"

OLLAMA_URL = os.getenv(
    "DOCDM_OLLAMA_URL",
    "http://localhost:11434/api/generate",
)

GEN_MODEL = os.getenv(
    "DOCDM_GEN_MODEL",
    "qwen2.5:7b",
)

JUDGE_MODEL = os.getenv(
    "DOCDM_JUDGE_MODEL",
    "qwen2.5:7b",
)

SEED = 42

MIN_CHARS_PER_PAGE = 200
MIN_CHUNK_WORDS = 80
MAX_CHUNK_WORDS = 250

MAX_DOCUMENTS = None
MAX_CHUNKS_PER_DOCUMENT = 50

REQUEST_TIMEOUT = 180

# Number of generated candidates per source chunk.
SUPPORTED_PER_CHUNK = 1
CONTRADICTED_PER_CHUNK = 1

# Keep this conservative.
MAX_GENERATION_RETRIES = 3

random.seed(SEED)


# ============================================================
# LABELS
# ============================================================

LABELS = {
    "supported": 0,
    "contradicted": 1,
    "not_mentioned": 2,
}


# ============================================================
# UTILITIES
# ============================================================

def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)


def normalize_whitespace(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            block = f.read(1024 * 1024)

            if not block:
                break

            h.update(block)

    return h.hexdigest()


def word_count(text: str) -> int:
    return len(text.split())


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                )
                + "\n"
            )


# ============================================================
# OLLAMA
# ============================================================

def ollama_generate(
    prompt: str,
    model: str,
    temperature: float = 0.2,
    retries: int = MAX_GENERATION_RETRIES,
) -> str:

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }

    last_error = None

    for attempt in range(1, retries + 1):

        try:
            response = requests.post(
                OLLAMA_URL,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )

            response.raise_for_status()

            data = response.json()

            text = data.get("response", "")

            if text:
                return text.strip()

            raise RuntimeError("Ollama returned an empty response.")

        except Exception as exc:

            last_error = exc

            print(
                f"  Ollama attempt {attempt}/{retries} failed: "
                f"{exc}"
            )

            if attempt < retries:
                time.sleep(2 * attempt)

    raise RuntimeError(
        f"Ollama generation failed after {retries} attempts: "
        f"{last_error}"
    )


# ============================================================
# JSON EXTRACTION
# ============================================================

def extract_json(text: str) -> dict[str, Any] | None:

    text = text.strip()

    # Direct JSON.
    try:
        value = json.loads(text)

        if isinstance(value, dict):
            return value

    except Exception:
        pass

    # JSON inside markdown fences.
    fenced = re.search(
        r"```(?:json)?\s*(\{.*?\})\s*```",
        text,
        flags=re.DOTALL,
    )

    if fenced:

        try:
            value = json.loads(fenced.group(1))

            if isinstance(value, dict):
                return value

        except Exception:
            pass

    # Find first object-looking block.
    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end > start:

        candidate = text[start : end + 1]

        try:
            value = json.loads(candidate)

            if isinstance(value, dict):
                return value

        except Exception:
            pass

    return None


# ============================================================
# PDF EXTRACTION
# ============================================================

def extract_pdf_pages(pdf_path: Path) -> list[dict[str, Any]]:

    pages = []

    try:
        document = fitz.open(pdf_path)

    except Exception as exc:

        print(f"  ERROR opening PDF: {exc}")

        return pages

    for page_number, page in enumerate(document):

        try:
            text = page.get_text("text")
        except Exception:
            text = ""

        text = normalize_whitespace(text)

        if len(text) < MIN_CHARS_PER_PAGE:
            continue

        pages.append(
            {
                "page_number": page_number + 1,
                "text": text,
            }
        )

    document.close()

    return pages


# ============================================================
# CHUNKING
# ============================================================

def split_into_chunks(
    text: str,
    min_words: int = MIN_CHUNK_WORDS,
    max_words: int = MAX_CHUNK_WORDS,
) -> list[str]:

    words = text.split()

    chunks = []

    start = 0

    while start < len(words):

        end = min(
            start + max_words,
            len(words),
        )

        chunk = " ".join(words[start:end]).strip()

        if word_count(chunk) >= min_words:
            chunks.append(chunk)

        start = end

    return chunks


def build_document_chunks(
    pdf_path: Path,
) -> list[dict[str, Any]]:

    pages = extract_pdf_pages(pdf_path)

    all_chunks = []

    for page in pages:

        chunks = split_into_chunks(
            page["text"]
        )

        for chunk_index, chunk in enumerate(chunks):

            all_chunks.append(
                {
                    "page_number": page["page_number"],
                    "chunk_index": chunk_index,
                    "text": chunk,
                }
            )

    return all_chunks


# ============================================================
# CLAIM GENERATION
# ============================================================

def generate_supported_claim(
    passage: str,
) -> str | None:

    prompt = f"""
You are creating a factual evidence-verification dataset.

Read the passage below.

Generate ONE factual claim that is explicitly supported
by the passage.

Rules:
- The claim must be directly supported by the passage.
- Do not add outside knowledge.
- Do not make the claim broader than the passage.
- Prefer concrete factual statements.
- Preserve important numbers, names, dates, quantities,
  relationships, and technical terms.
- Return ONLY the claim.
- No explanation.

PASSAGE:
{passage}
"""

    response = ollama_generate(
        prompt,
        GEN_MODEL,
        temperature=0.1,
    )

    response = normalize_whitespace(response)

    if not response:
        return None

    return response


def generate_contradiction(
    passage: str,
    supported_claim: str,
) -> str | None:

    prompt = f"""
You are creating a factual evidence-verification dataset.

PASSAGE:
{passage}

SUPPORTED CLAIM:
{supported_claim}

Create ONE claim that is clearly CONTRADICTED by the passage.

Rules:
- The passage must contain enough information to establish
  that the new claim is false.
- Change a factual proposition explicitly stated or clearly
  implied by the passage.
- If the passage contains a number, date, quantity, comparison,
  location, relationship, or named entity, you may alter it.
- Do NOT create a claim that is merely absent.
- Do NOT introduce unrelated outside information.
- Make the contradiction unambiguous.
- Return ONLY the contradictory claim.
- No explanation.

CONTRADICTORY CLAIM:
"""

    response = ollama_generate(
        prompt,
        GEN_MODEL,
        temperature=0.3,
    )

    response = normalize_whitespace(response)

    if not response:
        return None

    return response


# ============================================================
# NOT-MENTIONED CLAIM GENERATION
# ============================================================

def generate_not_mentioned_claim(
    source_passage: str,
    external_claim: str,
) -> str | None:

    prompt = f"""
You are creating a factual evidence-verification dataset.

CURRENT PASSAGE:
{source_passage}

REFERENCE CLAIM FROM ANOTHER DOCUMENT:
{external_claim}

Create ONE factual claim based on the reference claim that
is NOT stated or supported by the current passage.

Rules:
- The current passage must not explicitly support the claim.
- The claim should remain factual and coherent.
- Do not create a claim that is obviously unrelated nonsense.
- Do not alter the meaning unnecessarily.
- Return ONLY the claim.
- No explanation.

CLAIM:
"""

    response = ollama_generate(
        prompt,
        GEN_MODEL,
        temperature=0.3,
    )

    response = normalize_whitespace(response)

    if not response:
        return None

    return response


# ============================================================
# JUDGING
# ============================================================

def judge_claim(
    passage: str,
    claim: str,
    expected_label: str,
) -> dict[str, Any] | None:

    prompt = f"""
You are a strict evidence-verification judge.

Determine the relationship between the PASSAGE and CLAIM.

Allowed labels:

supported:
The passage directly supports the claim.

contradicted:
The passage contains information that makes the claim false.

not_mentioned:
The passage neither supports nor contradicts the claim.

PASSAGE:
{passage}

CLAIM:
{claim}

EXPECTED LABEL:
{expected_label}

Return ONLY valid JSON:

{{
  "label": "supported|contradicted|not_mentioned",
  "valid": true,
  "reason": "short explanation"
}}

Rules:
- Do not use outside knowledge.
- Use only the information contained in the passage.
- Be strict.
"""

    response = ollama_generate(
        prompt,
        JUDGE_MODEL,
        temperature=0.0,
    )

    result = extract_json(response)

    if not result:
        return None

    label = str(
        result.get("label", "")
    ).strip().lower()

    valid = result.get("valid", False)

    if label not in LABELS:
        return None

    return {
        "label": label,
        "valid": bool(valid),
        "reason": str(
            result.get("reason", "")
        ).strip(),
    }


# ============================================================
# DOCUMENT PROCESSING
# ============================================================

def create_supported_example(
    pdf_path: Path,
    document_id: str,
    chunk: dict[str, Any],
) -> dict[str, Any] | None:

    passage = chunk["text"]

    claim = generate_supported_claim(
        passage
    )

    if not claim:
        return None

    judgment = judge_claim(
        passage,
        claim,
        "supported",
    )

    if not judgment:
        return None

    if not judgment["valid"]:
        return None

    if judgment["label"] != "supported":
        return None

    return {
        "id": hashlib.sha256(
            f"{document_id}|"
            f"{chunk['page_number']}|"
            f"{chunk['chunk_index']}|"
            f"{claim}".encode("utf-8")
        ).hexdigest(),

        "task": "evidence",

        "label": "supported",

        "label_id": LABELS["supported"],

        "passage": passage,

        "claim": claim,

        "document_id": document_id,

        "source_file": pdf_path.name,

        "page_number": chunk["page_number"],

        "chunk_index": chunk["chunk_index"],

        "generation_model": GEN_MODEL,

        "judge_model": JUDGE_MODEL,

        "judge_reason": judgment["reason"],

        "synthetic": True,

        "provenance": {
            "source_type": "local_pdf",
            "source_file": pdf_path.name,
        },
    }


def create_contradicted_example(
    pdf_path: Path,
    document_id: str,
    chunk: dict[str, Any],
    supported_claim: str,
) -> dict[str, Any] | None:

    passage = chunk["text"]

    claim = generate_contradiction(
        passage,
        supported_claim,
    )

    if not claim:
        return None

    judgment = judge_claim(
        passage,
        claim,
        "contradicted",
    )

    if not judgment:
        return None

    if not judgment["valid"]:
        return None

    if judgment["label"] != "contradicted":
        return None

    return {
        "id": hashlib.sha256(
            f"{document_id}|"
            f"{chunk['page_number']}|"
            f"{chunk['chunk_index']}|"
            f"contradicted|{claim}".encode("utf-8")
        ).hexdigest(),

        "task": "evidence",

        "label": "contradicted",

        "label_id": LABELS["contradicted"],

        "passage": passage,

        "claim": claim,

        "document_id": document_id,

        "source_file": pdf_path.name,

        "page_number": chunk["page_number"],

        "chunk_index": chunk["chunk_index"],

        "generation_model": GEN_MODEL,

        "judge_model": JUDGE_MODEL,

        "judge_reason": judgment["reason"],

        "synthetic": True,

        "provenance": {
            "source_type": "local_pdf",
            "source_file": pdf_path.name,
        },
    }


# ============================================================
# MAIN DATA BUILD
# ============================================================

def build_raw_dataset(
    pdf_paths: list[Path],
) -> list[dict[str, Any]]:

    examples = []

    for document_number, pdf_path in enumerate(
        pdf_paths,
        start=1,
    ):

        print()
        print("=" * 70)
        print(
            f"DOCUMENT {document_number}/{len(pdf_paths)}"
        )
        print(pdf_path.name)
        print("=" * 70)

        document_id = sha256_file(
            pdf_path
        )

        chunks = build_document_chunks(
            pdf_path
        )

        if MAX_CHUNKS_PER_DOCUMENT:
            chunks = chunks[
                :MAX_CHUNKS_PER_DOCUMENT
            ]

        print(
            f"Extracted {len(chunks)} usable chunks"
        )

        if not chunks:
            continue

        for chunk_number, chunk in enumerate(
            chunks,
            start=1,
        ):

            print(
                f"  Chunk {chunk_number}/{len(chunks)}"
            )

            try:

                supported = create_supported_example(
                    pdf_path,
                    document_id,
                    chunk,
                )

                if supported:

                    examples.append(
                        supported
                    )

                    print(
                        "    + supported"
                    )

                    # Generate contradiction from the
                    # same passage/claim.
                    contradicted = (
                        create_contradicted_example(
                            pdf_path,
                            document_id,
                            chunk,
                            supported["claim"],
                        )
                    )

                    if contradicted:

                        examples.append(
                            contradicted
                        )

                        print(
                            "    + contradicted"
                        )

                    else:

                        print(
                            "    - contradiction rejected"
                        )

                else:

                    print(
                        "    - supported claim rejected"
                    )

            except Exception as exc:

                print(
                    f"    ERROR: {exc}"
                )

    return examples


# ============================================================
# NOT-MENTIONED BALANCING
# ============================================================

def add_not_mentioned_examples(
    examples: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    supported_claims = [
        row["claim"]
        for row in examples
        if row["label"] == "supported"
    ]

    passages = [
        row
        for row in examples
        if row["label"] == "supported"
    ]

    if len(supported_claims) < 2:
        return examples

    print()
    print("=" * 70)
    print("GENERATING NOT_MENTIONED EXAMPLES")
    print("=" * 70)

    candidates = []

    for current in passages:

        other = random.choice(
            supported_claims
        )

        if (
            other
            == current["claim"]
        ):
            continue

        try:

            claim = generate_not_mentioned_claim(
                current["passage"],
                other,
            )

            if not claim:
                continue

            judgment = judge_claim(
                current["passage"],
                claim,
                "not_mentioned",
            )

            if not judgment:
                continue

            if not judgment["valid"]:
                continue

            if judgment["label"] != "not_mentioned":
                continue

            row = {
                "id": hashlib.sha256(
                    f"{current['document_id']}|"
                    f"{current['page_number']}|"
                    f"not_mentioned|{claim}".encode(
                        "utf-8"
                    )
                ).hexdigest(),

                "task": "evidence",

                "label": "not_mentioned",

                "label_id": LABELS["not_mentioned"],

                "passage": current["passage"],

                "claim": claim,

                "document_id": current[
                    "document_id"
                ],

                "source_file": current[
                    "source_file"
                ],

                "page_number": current[
                    "page_number"
                ],

                "chunk_index": current[
                    "chunk_index"
                ],

                "generation_model": GEN_MODEL,

                "judge_model": JUDGE_MODEL,

                "judge_reason": judgment[
                    "reason"
                ],

                "synthetic": True,

                "provenance": {
                    "source_type": "local_pdf",
                    "source_file": current[
                        "source_file"
                    ],
                    "claim_source": "another_document",
                },
            }

            candidates.append(row)

            print(
                f"  + not_mentioned "
                f"({len(candidates)})"
            )

        except Exception as exc:

            print(
                f"  ERROR: {exc}"
            )

    return examples + candidates


# ============================================================
# DOCUMENT-LEVEL SPLIT
# ============================================================

def split_by_document(
    examples: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:

    document_ids = sorted(
        {
            row["document_id"]
            for row in examples
        }
    )

    random.Random(SEED).shuffle(
        document_ids
    )

    n = len(document_ids)

    train_end = int(
        n * 0.70
    )

    val_end = int(
        n * 0.85
    )

    train_documents = set(
        document_ids[:train_end]
    )

    val_documents = set(
        document_ids[
            train_end:val_end
        ]
    )

    test_documents = set(
        document_ids[val_end:]
    )

    train = []
    val = []
    test = []

    for row in examples:

        document_id = row[
            "document_id"
        ]

        if document_id in train_documents:
            train.append(row)

        elif document_id in val_documents:
            val.append(row)

        elif document_id in test_documents:
            test.append(row)

    return train, val, test


# ============================================================
# MANIFEST
# ============================================================

def build_manifest(
    pdf_paths: list[Path],
) -> list[dict[str, Any]]:

    manifest = []

    for pdf_path in pdf_paths:

        try:

            document_id = sha256_file(
                pdf_path
            )

            pages = extract_pdf_pages(
                pdf_path
            )

            manifest.append(
                {
                    "document_id": document_id,
                    "filename": pdf_path.name,
                    "path": str(
                        pdf_path.resolve()
                    ),
                    "pages_with_text": len(
                        pages
                    ),
                    "sha256": document_id,
                }
            )

        except Exception as exc:

            print(
                f"Manifest error for "
                f"{pdf_path.name}: {exc}"
            )

    return manifest


# ============================================================
# SUMMARY
# ============================================================

def print_summary(
    train: list[dict[str, Any]],
    val: list[dict[str, Any]],
    test: list[dict[str, Any]],
) -> None:

    print()
    print("=" * 70)
    print("DOCDM DATASET COMPLETE")
    print("=" * 70)

    print(
        f"Train examples : {len(train):,}"
    )

    print(
        f"Val examples   : {len(val):,}"
    )

    print(
        f"Test examples  : {len(test):,}"
    )

    print(
        f"Total examples : "
        f"{len(train) + len(val) + len(test):,}"
    )

    print()

    for name, rows in [
        ("TRAIN", train),
        ("VAL", val),
        ("TEST", test),
    ]:

        counts = {
            label: sum(
                row["label"] == label
                for row in rows
            )
            for label in LABELS
        }

        print(
            f"{name}: "
            f"supported={counts['supported']:,}, "
            f"contradicted={counts['contradicted']:,}, "
            f"not_mentioned={counts['not_mentioned']:,}"
        )

    print()
    print(
        f"Saved to: {DATA_DIR.resolve()}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("DOCDM-EVIDENCE DATA BUILDER")
    print("=" * 70)

    print(
        f"PDF directory : {PDF_DIR.resolve()}"
    )

    print(
        f"Data directory: {DATA_DIR.resolve()}"
    )

    print(
        f"Generation LLM: {GEN_MODEL}"
    )

    print(
        f"Judge LLM     : {JUDGE_MODEL}"
    )

    ensure_directories()

    # --------------------------------------------------------
    # Find PDFs
    # --------------------------------------------------------

    pdf_paths = sorted(
        PDF_DIR.glob("*.pdf")
    )

    if MAX_DOCUMENTS is not None:

        pdf_paths = pdf_paths[
            :MAX_DOCUMENTS
        ]

    if not pdf_paths:

        print()
        print(
            "ERROR: No PDF files found."
        )

        print()
        print(
            f"Put your PDFs inside:"
        )

        print(
            f"  {PDF_DIR.resolve()}"
        )

        return

    print()
    print(
        f"Found {len(pdf_paths):,} PDF files."
    )

    # --------------------------------------------------------
    # Check Ollama
    # --------------------------------------------------------

    print()
    print(
        "Checking Ollama..."
    )

    try:

        response = requests.get(
            "http://localhost:11434/api/tags",
            timeout=10,
        )

        response.raise_for_status()

        models = response.json().get(
            "models",
            []
        )

        model_names = [
            m.get("name", "")
            for m in models
        ]

        print(
            f"Ollama online. "
            f"{len(model_names)} model(s) available."
        )

        if GEN_MODEL not in model_names:
            print(
                f"WARNING: {GEN_MODEL} "
                f"was not found in Ollama."
            )

        if JUDGE_MODEL not in model_names:
            print(
                f"WARNING: {JUDGE_MODEL} "
                f"was not found in Ollama."
            )

    except Exception as exc:

        print()
        print(
            "ERROR: Ollama is not reachable."
        )

        print(
            f"URL: {OLLAMA_URL}"
        )

        print(
            f"Reason: {exc}"
        )

        print()
        print(
            "Start Ollama and make sure the selected "
            "models are installed."
        )

        return

    # --------------------------------------------------------
    # Manifest
    # --------------------------------------------------------

    print()
    print(
        "Building document manifest..."
    )

    manifest = build_manifest(
        pdf_paths
    )

    write_jsonl(
        MANIFEST_OUTPUT,
        manifest,
    )

    print(
        f"Manifest saved: "
        f"{MANIFEST_OUTPUT}"
    )

    # --------------------------------------------------------
    # Generate supported + contradicted
    # --------------------------------------------------------

    examples = build_raw_dataset(
        pdf_paths
    )

    print()
    print(
        f"Generated {len(examples):,} "
        "supported/contradicted candidates."
    )

    # --------------------------------------------------------
    # Generate not mentioned
    # --------------------------------------------------------

    examples = add_not_mentioned_examples(
        examples
    )

    # --------------------------------------------------------
    # Remove duplicate IDs
    # --------------------------------------------------------

    unique = {}

    for row in examples:
        unique[row["id"]] = row

    examples = list(
        unique.values()
    )

    random.Random(SEED).shuffle(
        examples
    )

    # --------------------------------------------------------
    # Save raw dataset
    # --------------------------------------------------------

    write_jsonl(
        RAW_OUTPUT,
        examples,
    )

    print()
    print(
        f"Raw dataset saved: "
        f"{RAW_OUTPUT}"
    )

    # --------------------------------------------------------
    # Document-level split
    # --------------------------------------------------------

    train, val, test = split_by_document(
        examples
    )

    # --------------------------------------------------------
    # Save splits
    # --------------------------------------------------------

    write_jsonl(
        TRAIN_OUTPUT,
        train,
    )

    write_jsonl(
        VAL_OUTPUT,
        val,
    )

    write_jsonl(
        TEST_OUTPUT,
        test,
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print_summary(
        train,
        val,
        test,
    )

    print()
    print(
        "Next step: inspect the JSONL data before training DocDM."
    )


if __name__ == "__main__":
    main()