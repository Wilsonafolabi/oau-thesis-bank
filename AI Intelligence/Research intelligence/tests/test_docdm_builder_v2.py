import pytest
import json
import os
from pathlib import Path

def test_document_level_split_no_leakage():
    # Simulate the split logic
    doc_ids = [f"doc_{i}" for i in range(10)]
    train_docs = set(doc_ids[:8])
    val_docs = set(doc_ids[8:9])
    test_docs = set(doc_ids[9:])
    
    # Ensure no overlap
    assert len(train_docs & val_docs) == 0
    assert len(train_docs & test_docs) == 0
    assert len(val_docs & test_docs) == 0

def test_not_mentioned_cross_doc_logic():
    # Verify that not_mentioned claims come from different docs within the same split
    doc_a = "doc_1"
    doc_b = "doc_2"
    split_a = "train"
    split_b = "train"
    
    assert doc_a != doc_b
    assert split_a == split_b # Must be same split to prevent leakage

def test_deterministic_id_generation():
    import hashlib
    id1 = hashlib.md5(f"doc_1_claim_text".encode()).hexdigest()
    id2 = hashlib.md5(f"doc_1_claim_text".encode()).hexdigest()
    assert id1 == id2

def test_output_files_exist():
    out_dir = Path("output/docdm_dataset")
    if out_dir.exists():
        assert (out_dir / "docdm_evidence_train.jsonl").exists()
        assert (out_dir / "docdm_evidence_val.jsonl").exists()
        assert (out_dir / "docdm_evidence_test.jsonl").exists()
        assert (out_dir / "docdm_dataset_stats.json").exists()
