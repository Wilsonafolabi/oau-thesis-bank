"""P5 regression tests — similarity, plagiarism assessment, AI-writing detection.

Deterministic. Database sessions are mocked; the AI-writing detector is tested
only for its explicit availability contract, because no model weights exist
locally and downloads are forbidden.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pathlib import Path

from oau_ai.ai_writing.service import (
    AITextDetectionService,
    MIN_WORDS,
    STATUS_INSUFFICIENT_TEXT,
    STATUS_UNAVAILABLE,
    STATUS_UNSUPPORTED_LANGUAGE,
)
from oau_ai.auth.middleware import ActorContext
from oau_ai.errors import Phase3Error
from oau_ai.similarity.service import (
    ATTRIBUTION_PRESENT,
    MAX_TEXT_CHARS,
    NO_SIGNIFICANT_OVERLAP,
    REVIEW_REQUIRED,
    PlagiarismAssessmentService,
    SimilarityMatch,
    SimilarityResult,
    SimilarityService,
    split_passages,
)

SOURCE_TEXT = (
    "crop rotation improves soil nitrogen availability in smallholder farms "
    "across the region"
)


def _actor(user_id="user-1"):
    return ActorContext(user_id=user_id, roles=["student"], department="CS", trace_id="t-p5")


def _chunk(text, chunk_id="c1"):
    chunk = MagicMock()
    chunk.id = chunk_id
    chunk.text = text
    return chunk


def _doc(doc_id="doc-1", thesis_id="1", title="Soil study"):
    document = MagicMock()
    document.id = doc_id
    document.backend_thesis_id = thesis_id
    document.thesis_metadata = {"title": title}
    return document


class _ChunkSession:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    async def execute(self, statement, *args, **kwargs):
        self.queries.append(str(statement))
        result = MagicMock()
        result.all.return_value = self.rows
        return result

    async def close(self):
        return None


def _service(rows, **kwargs):
    return SimilarityService(
        db_session=_ChunkSession(rows), enable_semantic=kwargs.pop("enable_semantic", False), **kwargs
    )


# --------------------------------------------------------------------------
# Capability A — similarity
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exact_copied_passage_is_detected():
    service = _service([(_chunk(SOURCE_TEXT), _doc())])

    result = await service.compare_text(_actor(), SOURCE_TEXT)

    assert len(result.matches) == 1
    assert result.matches[0].match_type == "exact"
    assert result.matches[0].score == pytest.approx(1.0, abs=0.01)
    assert result.matches[0].backend_thesis_id == "1"


@pytest.mark.asyncio
async def test_minor_edit_is_near_exact():
    service = _service([(_chunk(SOURCE_TEXT), _doc())])
    edited = SOURCE_TEXT.replace("region", "district")

    result = await service.compare_text(_actor(), edited)

    assert result.matches
    assert result.matches[0].match_type == "near_exact"
    assert 0.5 <= result.matches[0].score < 1.0


@pytest.mark.asyncio
async def test_paraphrase_does_not_produce_a_lexical_match():
    service = _service([(_chunk(SOURCE_TEXT), _doc())])
    paraphrase = "rotating crops boosts nitrogen in the soil for small farms"

    result = await service.compare_text(_actor(), paraphrase, min_score=0.5)

    assert result.matches == []


@pytest.mark.asyncio
async def test_unrelated_text_has_no_matches():
    service = _service([(_chunk(SOURCE_TEXT), _doc())])

    result = await service.compare_text(
        _actor(), "machine learning models for credit scoring decisions"
    )

    assert result.matches == []
    assert result.exact_matches == []


@pytest.mark.asyncio
async def test_duplicate_rows_are_deduplicated():
    chunk, document = _chunk(SOURCE_TEXT), _doc()
    service = _service([(chunk, document), (chunk, document)])

    result = await service.compare_text(_actor(), SOURCE_TEXT)

    assert len(result.matches) == 1


@pytest.mark.asyncio
async def test_empty_input_is_rejected():
    service = _service([])

    with pytest.raises(Phase3Error) as exc:
        await service.compare_text(_actor(), "   ")

    assert exc.value.code == "empty_text"


@pytest.mark.asyncio
async def test_oversized_input_is_rejected():
    service = _service([])

    with pytest.raises(Phase3Error) as exc:
        await service.compare_text(_actor(), "word " * (MAX_TEXT_CHARS // 2))

    assert exc.value.code == "text_too_large"


@pytest.mark.asyncio
async def test_excluded_document_is_not_compared():
    chunk, document = _chunk(SOURCE_TEXT), _doc(doc_id="doc-9")
    service = _service([(chunk, document)])

    result = await service.compare_text(
        _actor(), SOURCE_TEXT, exclude_document_ids=["doc-9"]
    )

    assert result.matches == []


@pytest.mark.asyncio
async def test_private_documents_are_excluded_by_the_query():
    session = _ChunkSession([])
    service = SimilarityService(db_session=session, enable_semantic=False)

    await service.compare_text(_actor(), SOURCE_TEXT)

    query = session.queries[0]
    assert "access_level" in query or "backend_user_id" in query


@pytest.mark.asyncio
async def test_no_accessible_documents_is_disclosed():
    service = _service([])

    result = await service.compare_text(_actor(), SOURCE_TEXT)

    assert result.matches == []
    assert any("No accessible repository documents" in note for note in result.limitations)


@pytest.mark.asyncio
async def test_semantic_absence_is_disclosed():
    service = _service([(_chunk(SOURCE_TEXT), _doc())], enable_semantic=True)

    result = await service.compare_text(_actor(), SOURCE_TEXT)

    assert any("lexical" in note for note in result.limitations)


@pytest.mark.asyncio
async def test_max_matches_caps_results():
    rows = [(_chunk(SOURCE_TEXT, f"c{i}"), _doc(doc_id=f"d{i}")) for i in range(6)]
    service = _service(rows)

    result = await service.compare_text(_actor(), SOURCE_TEXT, max_matches=2)

    assert len(result.matches) == 2


def test_passages_are_bounded():
    text = " ".join(f"w{i}" for i in range(1000))

    passages = split_passages(text, words_per_passage=100)

    assert all(len(p.split()) <= 100 for p in passages)
    assert len(passages) == 10


# --------------------------------------------------------------------------
# Capability B — plagiarism assessment
# --------------------------------------------------------------------------


def _similarity_stub(matches):
    stub = MagicMock()
    stub.compare_text = AsyncMock(
        return_value=SimilarityResult(
            input_mode="text",
            passages_scanned=1,
            chunks_scanned=1,
            matches=matches,
            exact_matches=matches,
            semantic_matches=[],
            limitations=[],
        )
    )
    return stub


def _match(excerpt, doc_id="doc-1", thesis_id="1", chunk_id="c1"):
    return SimilarityMatch(
        match_type="exact",
        score=1.0,
        document_id=doc_id,
        backend_thesis_id=thesis_id,
        title="Soil study",
        chunk_id=chunk_id,
        page_number=None,
        source_excerpt=SOURCE_TEXT,
        submitted_excerpt=excerpt,
    )


@pytest.mark.asyncio
async def test_verbatim_overlap_without_attribution_needs_review():
    service = PlagiarismAssessmentService(similarity_service=_similarity_stub([_match(SOURCE_TEXT[:300])]))

    result = await service.assess(_actor(), SOURCE_TEXT)

    assert result.status == REVIEW_REQUIRED
    assert result.passages[0].assessment == REVIEW_REQUIRED
    assert result.passages[0].quoted is False
    assert result.passages[0].cited is False


@pytest.mark.asyncio
async def test_quoted_passage_is_attributed():
    excerpt = SOURCE_TEXT[:300]
    text = f'As one author notes, "{excerpt}" which is widely reported.'
    service = PlagiarismAssessmentService(similarity_service=_similarity_stub([_match(excerpt)]))

    result = await service.assess(_actor(), text)

    assert result.status == ATTRIBUTION_PRESENT
    assert result.passages[0].quoted is True


@pytest.mark.asyncio
async def test_cited_passage_is_attributed():
    excerpt = SOURCE_TEXT[:300]
    text = f"{excerpt} (Adeyemi, 2019)."
    service = PlagiarismAssessmentService(similarity_service=_similarity_stub([_match(excerpt)]))

    result = await service.assess(_actor(), text)

    assert result.status == ATTRIBUTION_PRESENT
    assert result.passages[0].cited is True


@pytest.mark.asyncio
async def test_multiple_sources_are_counted():
    matches = [
        _match(SOURCE_TEXT[:300], doc_id="doc-1", chunk_id="c1"),
        _match(SOURCE_TEXT[:300], doc_id="doc-2", thesis_id="2", chunk_id="c2"),
    ]
    service = PlagiarismAssessmentService(similarity_service=_similarity_stub(matches))

    result = await service.assess(_actor(), SOURCE_TEXT)

    assert result.matched_source_count == 2


@pytest.mark.asyncio
async def test_no_overlap_reports_no_significant_overlap():
    service = PlagiarismAssessmentService(similarity_service=_similarity_stub([]))

    result = await service.assess(_actor(), "entirely unrelated content")

    assert result.status == NO_SIGNIFICANT_OVERLAP
    assert result.passages == []


@pytest.mark.asyncio
async def test_assessment_never_issues_a_verdict():
    service = PlagiarismAssessmentService(similarity_service=_similarity_stub([_match(SOURCE_TEXT[:300])]))

    result = await service.assess(_actor(), SOURCE_TEXT)

    assert "not a finding of plagiarism" in result.disclaimer
    assert result.status != "plagiarism"


# --------------------------------------------------------------------------
# Capability C — AI-writing detection (availability contract only)
# --------------------------------------------------------------------------


def test_detector_reports_unavailable_without_weights(tmp_path):
    service = AITextDetectionService(model_root=str(tmp_path))

    result = service.detect("word " * (MIN_WORDS + 10))

    assert result.status == STATUS_UNAVAILABLE
    assert result.ai_probability is None
    assert result.confidence is None
    assert result.segments == []
    assert "Weights" in result.blocker or "weights" in result.blocker
    assert "not proof" in result.disclaimer


def test_detector_rejects_short_text(tmp_path):
    service = AITextDetectionService(model_root=str(tmp_path))

    result = service.detect("too short to judge")

    assert result.status == STATUS_INSUFFICIENT_TEXT
    assert result.ai_probability is None


def test_detector_rejects_unsupported_script(tmp_path):
    service = AITextDetectionService(model_root=str(tmp_path))
    text = "这是一个用于测试的中文段落" * 10

    result = service.detect(text)

    assert result.status == STATUS_UNSUPPORTED_LANGUAGE
    assert result.ai_probability is None


def test_detector_rejects_empty_text(tmp_path):
    service = AITextDetectionService(model_root=str(tmp_path))

    assert service.detect("").status == STATUS_INSUFFICIENT_TEXT


def test_availability_reports_blocker(tmp_path):
    service = AITextDetectionService(model_root=str(tmp_path))

    available, blocker = service.availability()

    assert available is False
    assert blocker


def test_segmentation_bounds_segment_size(tmp_path):
    service = AITextDetectionService(model_root=str(tmp_path))
    text = " ".join(f"word{i}" for i in range(300))

    segments = service._segment(text)

    assert len(segments) >= 2
    assert all(len(segment[0].split()) <= 120 for segment in segments)


def test_confidence_is_zero_for_single_segment():
    from oau_ai.ai_writing.service import SegmentResult

    single = [SegmentResult("t", 0, 1, 0.8, "likely_ai")]

    assert AITextDetectionService._confidence(single) == 0.0


def test_bands_are_explicit():
    assert AITextDetectionService._band(0.9) == "likely_ai"
    assert AITextDetectionService._band(0.5) == "uncertain"
    assert AITextDetectionService._band(0.1) == "likely_human"


def test_injected_predictor_scores_segments(tmp_path):
    service = AITextDetectionService(
        model_root=str(tmp_path), predictor=lambda text: 0.9
    )
    text = " ".join(["word"] * 130)

    result = service.detect(text)

    assert result.status == "ok"
    assert result.ai_probability == pytest.approx(0.9, abs=1e-4)
    assert len(result.segments) == 2
    assert result.assessment == "likely_ai"
    # An injected predictor is not the calibrated model.
    assert result.calibration is None


def test_local_detector_model_is_released_after_scoring(tmp_path, monkeypatch):
    from unittest.mock import Mock

    import oau_ai.ai_writing.service as detector_module

    model = Mock()
    service = AITextDetectionService(model_root=str(tmp_path))
    service._backend = {"model": model}
    monkeypatch.setattr(service, "_score", lambda texts: [0.8])
    monkeypatch.setattr(detector_module, "clear_cuda_cache", lambda: None)

    result = service.detect(" ".join(["research"] * 80))

    assert result.status == "ok"
    model.to.assert_called_once_with("cpu")
    assert service._backend is None


def test_injected_predictor_reports_low_scores(tmp_path):
    service = AITextDetectionService(
        model_root=str(tmp_path), predictor=lambda text: 0.05
    )

    result = service.detect(" ".join(["word"] * 80))

    assert result.status == "ok"
    assert result.assessment == "likely_human"


def test_inference_failure_is_not_reported_as_success(tmp_path):
    def boom(text):
        raise RuntimeError("cuda exploded")

    service = AITextDetectionService(model_root=str(tmp_path), predictor=boom)

    result = service.detect(" ".join(["word"] * 80))

    assert result.status == STATUS_UNAVAILABLE
    assert result.ai_probability is None
    assert "Inference failed" in result.blocker


DETECTOR_DIR = (
    Path(__file__).resolve().parents[3]
    / "models"
    / "ai-text-detector-modernbert"
    / "snapshot"
)


@pytest.mark.skipif(
    not (DETECTOR_DIR / "model.safetensors").exists(),
    reason="detector weights not present",
)
def test_real_model_produces_a_calibrated_score():
    """Integration: the pinned classifier actually loads and scores text."""
    service = AITextDetectionService()

    result = service.detect(
        "This study examined the effect of crop rotation on soil nitrogen "
        "availability in smallholder farms in Oyo State between 2019 and 2022. "
        "Data were collected from forty plots using a randomised complete block "
        "design over four cropping seasons. Nitrogen content was measured at "
        "four intervals and analysis of variance was used to compare treatment "
        "means at the five percent level of significance. The results showed a "
        "consistent increase in available nitrogen under rotation."
    )

    assert result.status == "ok"
    assert 0.0 <= result.ai_probability <= 1.0
    assert result.calibration == "temperature_scaled"
    assert result.model_id == "rasbt/ai-text-detector-modernbert"
    assert result.segments
    assert result.confidence is not None


@pytest.mark.skipif(
    not (DETECTOR_DIR / "model.safetensors").exists(),
    reason="detector weights not present",
)
def test_real_model_label_index_comes_from_config():
    """The AI class index is read from the model config, never assumed."""
    service = AITextDetectionService()

    available, blocker = service.availability()

    assert available is True, blocker
    assert service._backend["ai_index"] == 1
    assert service._backend["temperature"] == pytest.approx(1.566228609277514)


# --------------------------------------------------------------------------
# Semantic path — vector hits must be re-resolved against the database
# --------------------------------------------------------------------------


def _semantic_service(resolved, unresolved, hits, query_error=None):
    from oau_ai.retrieval.service import AuthorizedChunk

    embedding = MagicMock()
    embedding.embed_text = MagicMock(return_value=MagicMock(vector=[0.1, 0.2, 0.3]))

    vectorize = MagicMock()
    vectorize.is_configured = MagicMock(return_value=True)
    if query_error is not None:
        vectorize.query = MagicMock(side_effect=query_error)
    else:
        vectorize.query = MagicMock(return_value={"result": {"matches": hits}})

    retrieval = MagicMock()
    retrieval.resolve_authorized_chunks = AsyncMock(return_value=(resolved, unresolved))

    service = SimilarityService(
        db_session=_ChunkSession([]),
        embedding_service=embedding,
        vectorize_service=vectorize,
        enable_semantic=True,
        retrieval_service=retrieval,
    )
    return service, AuthorizedChunk


@pytest.mark.asyncio
async def test_semantic_hit_is_re_resolved_against_the_database():
    from oau_ai.retrieval.service import AuthorizedChunk

    resolved = {
        "c1": AuthorizedChunk(
            chunk_id="c1",
            document_id="doc-1",
            backend_thesis_id="1",
            text="database text for the chunk",
            page_number=4,
            section=None,
            chunk_index=0,
            access_level="public",
            provenance={"source_file": "Soil study"},
        )
    }
    hits = [
        {
            "score": 0.82,
            "metadata": {"chunk_id": "c1", "document_id": "doc-1", "backend_thesis_id": "1"},
        }
    ]
    service, _ = _semantic_service(resolved, [], hits)

    result = await service.compare_text(_actor(), SOURCE_TEXT)

    semantic = [m for m in result.matches if m.match_type == "semantic"]
    assert len(semantic) == 1
    # Text and page come from the database record, not from Vectorize metadata.
    assert semantic[0].source_excerpt.startswith("database text")
    assert semantic[0].page_number == 4
    assert semantic[0].backend_thesis_id == "1"


@pytest.mark.asyncio
async def test_semantic_hit_for_unresolvable_chunk_is_dropped():
    hits = [
        {
            "score": 0.95,
            "metadata": {"chunk_id": "c-gone", "document_id": "doc-9"},
        }
    ]
    service, _ = _semantic_service({}, ["c-gone"], hits)

    result = await service.compare_text(_actor(), SOURCE_TEXT)

    assert result.matches == []


@pytest.mark.asyncio
async def test_semantic_failure_degrades_to_lexical():
    service, _ = _semantic_service(
        {}, [], [], query_error=RuntimeError("vector index down")
    )

    result = await service.compare_text(_actor(), SOURCE_TEXT)

    assert result.matches == []
    assert any("Semantic comparison failed" in note for note in result.limitations)


@pytest.mark.asyncio
async def test_semantic_scores_below_threshold_are_ignored():
    hits = [{"score": 0.05, "metadata": {"chunk_id": "c1", "document_id": "doc-1"}}]
    service, _ = _semantic_service({}, [], hits)

    result = await service.compare_text(_actor(), SOURCE_TEXT, min_score=0.4)

    assert result.matches == []
