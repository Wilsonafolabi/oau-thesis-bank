"""AI-writing detection using a locally hosted ModernBERT classifier.

Model: ``rasbt/ai-text-detector-modernbert``, revision
``a6efd4bf6ecd852f332b2569ae0f98cae13b7985``, licence Apache-2.0,
fine-tuned from ``answerdotai/ModernBERT-base``.

Inference follows the model card exactly:
- label mapping comes from ``detector-config.json`` (human=0, ai=1) — the AI
  index is never assumed;
- logits are divided by the published temperature (1.566228609277514) before
  softmax, so the reported value is the authors' temperature-scaled score;
- sequences are truncated to the configured 8192 tokens.

Even calibrated, the score is a probabilistic signal about a text, not evidence
about a person. The service refuses to report a score when inference did not run.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..local_model_runtime import MODEL_RUNTIME_LOCK, clear_cuda_cache

logger = logging.getLogger("oau_ai.ai_writing")

MODEL_ID = "rasbt/ai-text-detector-modernbert"
MODEL_REVISION = "a6efd4bf6ecd852f332b2569ae0f98cae13b7985"
MODEL_LICENSE = "Apache-2.0"

MIN_WORDS = 60
MAX_CHARS = 50_000
SEGMENT_WORDS = 120
MAX_SEGMENTS = 40

WEIGHT_FILES = ("model.safetensors", "pytorch_model.bin")

LIKELY_AI_BAND = 0.75
LIKELY_HUMAN_BAND = 0.35

STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"
STATUS_INSUFFICIENT_TEXT = "insufficient_text"
STATUS_UNSUPPORTED_LANGUAGE = "unsupported_language"

DISCLAIMER = (
    "AI-writing detection returns a probabilistic signal about a text, not "
    "evidence about its author. It is not proof of AI authorship and must not "
    "be used as an automated misconduct finding."
)

_LATIN_RE = re.compile(r"[A-Za-z]")


@dataclass
class SegmentResult:
    text: str
    start_char: int
    end_char: int
    ai_probability: float
    band: str  # likely_ai | uncertain | likely_human


@dataclass
class AITextDetectionResult:
    status: str
    assessment: Optional[str] = None
    ai_probability: Optional[float] = None
    confidence: Optional[float] = None
    segments: List[SegmentResult] = field(default_factory=list)
    model_id: Optional[str] = None
    model_version: Optional[str] = None
    calibration: Optional[str] = None
    limitations: List[str] = field(default_factory=list)
    blocker: Optional[str] = None
    disclaimer: str = DISCLAIMER


def _default_model_root() -> Path:
    return Path(
        os.getenv(
            "AI_TEXT_DETECTOR_PATH",
            str(
                Path(__file__).resolve().parents[5]
                / "models"
                / "ai-text-detector-modernbert"
                / "snapshot"
            ),
        )
    )


class AITextDetectionService:
    """Segmented AI-writing detection backed by a real local classifier."""

    def __init__(self, model_root: Optional[str] = None, predictor=None) -> None:
        self.model_root = Path(model_root) if model_root else _default_model_root()
        self._predictor = predictor
        self._backend: Optional[dict] = None
        self._blocker: Optional[str] = None

    # -- availability -----------------------------------------------------

    def _weights_present(self) -> bool:
        if not self.model_root.exists():
            return False
        for path in self.model_root.rglob("*"):
            if path.is_file() and path.name in WEIGHT_FILES and path.stat().st_size > 0:
                return True
        return False

    def availability(self) -> tuple:
        """Return (available, blocker). Never raises."""
        if self._predictor is not None or self._backend is not None:
            return True, None
        if self._blocker is not None:
            return False, self._blocker
        if not self.model_root.exists():
            self._blocker = f"Detector model directory not found at {self.model_root}."
            return False, self._blocker
        if not self._weights_present():
            self._blocker = (
                f"Weights for {MODEL_ID} are not present locally "
                f"({self.model_root} has no populated weight file). Detection "
                "requires the pinned weights to be downloaded first."
            )
            return False, self._blocker
        try:
            self._backend = self._load_backend()
            return True, None
        except Exception as exc:  # noqa: BLE001
            self._blocker = f"Detector failed to load: {exc}"
            logger.warning("ai_writing.load_failed: %s", exc)
            return False, self._blocker

    def _load_backend(self) -> dict:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        meta = {}
        config_path = self.model_root / "detector-config.json"
        if config_path.exists():
            meta = json.loads(config_path.read_text(encoding="utf-8"))

        tokenizer = AutoTokenizer.from_pretrained(str(self.model_root))
        model = AutoModelForSequenceClassification.from_pretrained(str(self.model_root))
        model.eval()

        label_mapping = meta.get("label_mapping") or {}
        config_map = getattr(model.config, "label2id", None) or {}
        ai_index = int(label_mapping.get("ai", config_map.get("AI", 1)))

        logger.info(
            "ai_writing.loaded model=%s revision=%s ai_index=%d temperature=%s",
            MODEL_ID,
            MODEL_REVISION,
            ai_index,
            meta.get("temperature"),
        )

        return {
            "torch": torch,
            "tokenizer": tokenizer,
            "model": model,
            "ai_index": ai_index,
            "temperature": float(meta.get("temperature", 1.0)),
            "threshold": float(meta.get("decision_threshold", 0.5)),
            "max_length": int(meta.get("max_length", 8192)),
        }

    # -- detection --------------------------------------------------------

    @staticmethod
    def _is_latin(text: str) -> bool:
        letters = [ch for ch in text if ch.isalpha()]
        if not letters:
            return False
        return (len(_LATIN_RE.findall(text)) / len(letters)) >= 0.6

    def detect(self, text: str) -> AITextDetectionResult:
        if text is None or not text.strip():
            return AITextDetectionResult(
                status=STATUS_INSUFFICIENT_TEXT,
                model_id=MODEL_ID,
                model_version=MODEL_REVISION,
                limitations=["No text was supplied."],
            )

        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS]

        # Script is a character-level property, so it is checked before length:
        # space-delimited word counts are meaningless for non-Latin scripts.
        if not self._is_latin(text):
            return AITextDetectionResult(
                status=STATUS_UNSUPPORTED_LANGUAGE,
                model_id=MODEL_ID,
                model_version=MODEL_REVISION,
                limitations=[
                    "The detector was fine-tuned on English text; this input is "
                    "outside its supported language range.",
                ],
            )

        word_count = len(text.split())
        if word_count < MIN_WORDS:
            return AITextDetectionResult(
                status=STATUS_INSUFFICIENT_TEXT,
                model_id=MODEL_ID,
                model_version=MODEL_REVISION,
                limitations=[
                    f"At least {MIN_WORDS} words are required for a meaningful "
                    f"signal; {word_count} were supplied.",
                ],
            )

        segments = self._segment(text)
        if not segments:
            return AITextDetectionResult(
                status=STATUS_INSUFFICIENT_TEXT,
                model_id=MODEL_ID,
                model_version=MODEL_REVISION,
                limitations=["No segment could be scored."],
            )

        try:
            with MODEL_RUNTIME_LOCK:
                available, blocker = self.availability()
                if not available:
                    return AITextDetectionResult(
                        status=STATUS_UNAVAILABLE,
                        model_id=MODEL_ID,
                        model_version=MODEL_REVISION,
                        blocker=blocker,
                        limitations=["No detection was performed, so no score is reported."],
                    )
                used_real_model = self._backend is not None
                try:
                    probabilities = self._score([segment[0] for segment in segments])
                finally:
                    self.release_device_memory()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ai_writing.inference_failed: %s", exc)
            return AITextDetectionResult(
                status=STATUS_UNAVAILABLE,
                model_id=MODEL_ID,
                model_version=MODEL_REVISION,
                blocker=f"Inference failed: {exc}",
                limitations=["No detection was performed, so no score is reported."],
            )

        results = [
            SegmentResult(
                text=segment_text,
                start_char=start,
                end_char=end,
                ai_probability=round(probability, 4),
                band=self._band(probability),
            )
            for (segment_text, start, end), probability in zip(segments, probabilities)
        ]

        mean_probability = sum(r.ai_probability for r in results) / len(results)
        return AITextDetectionResult(
            status=STATUS_OK,
            assessment=self._band(mean_probability),
            ai_probability=round(mean_probability, 4),
            confidence=self._confidence(results),
            segments=results,
            model_id=MODEL_ID,
            model_version=MODEL_REVISION,
            # Only a real backend applies the model's published temperature.
            calibration="temperature_scaled" if used_real_model else None,
            limitations=[
                "Trained on English human-vs-AI text from `rasbt/human-vs-ai-50k`; "
                "performance on OAU theses is not established.",
                "Short or technical prose can score as AI-generated even when "
                "human-written (observed false positives on licence and "
                "repository documentation text).",
                "Edited or lightly paraphrased machine text commonly evades "
                "detection.",
                "The score is a property of the text, not of its author.",
            ],
        )

    def release_device_memory(self) -> None:
        with MODEL_RUNTIME_LOCK:
            backend = self._backend
            if backend is not None:
                try:
                    backend["model"].to("cpu")
                except Exception:
                    pass
                self._backend = None
            clear_cuda_cache()

    def _score(self, texts: List[str]) -> List[float]:
        """Return the AI-class probability for each text."""
        if self._predictor is not None:
            return [float(self._predictor(text)) for text in texts]

        backend = self._backend
        torch = backend["torch"]
        inputs = backend["tokenizer"](
            texts,
            truncation=True,
            max_length=backend["max_length"],
            padding=True,
            return_tensors="pt",
        )
        with torch.inference_mode():
            logits = backend["model"](**inputs).logits / backend["temperature"]
            probabilities = logits.float().softmax(dim=-1)
        index = backend["ai_index"]
        return [float(row[index].item()) for row in probabilities]

    @staticmethod
    def _band(probability: float) -> str:
        if probability >= LIKELY_AI_BAND:
            return "likely_ai"
        if probability <= LIKELY_HUMAN_BAND:
            return "likely_human"
        return "uncertain"

    @staticmethod
    def _confidence(segments: List[SegmentResult]) -> float:
        """Agreement across segments (a spread measure, not model certainty)."""
        if len(segments) < 2:
            return 0.0
        mean = sum(s.ai_probability for s in segments) / len(segments)
        variance = sum((s.ai_probability - mean) ** 2 for s in segments) / len(segments)
        return round(max(0.0, 1.0 - (variance ** 0.5) * 2.0), 3)

    @staticmethod
    def _segment(text: str) -> List[tuple]:
        words = text.split()
        segments = []
        cursor = 0
        for start in range(0, len(words), SEGMENT_WORDS):
            chunk_words = words[start : start + SEGMENT_WORDS]
            if not chunk_words:
                continue
            segment_text = " ".join(chunk_words)
            begin = text.find(segment_text, cursor)
            if begin < 0:
                begin = cursor
            end = begin + len(segment_text)
            cursor = end
            segments.append((segment_text, begin, end))
            if len(segments) >= MAX_SEGMENTS:
                break
        return segments


_DETECTOR: Optional[AITextDetectionService] = None


def get_detection_service() -> AITextDetectionService:
    """Process-wide detector so the model is loaded once, not per request."""
    global _DETECTOR
    if _DETECTOR is None:
        _DETECTOR = AITextDetectionService()
    return _DETECTOR
