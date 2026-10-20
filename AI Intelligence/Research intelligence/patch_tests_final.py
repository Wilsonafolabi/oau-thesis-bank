with open("tests/test_nemoguardrails_runtime.py", "r", encoding="utf-8") as f:
    text = f.read()

# Fix test_10: Provide dummy evidence so it passes require_evidence and actually hits the FailRouter
text = text.replace(
    'user_input="Explain the methodology of the thesis in detail"))',
    'user_input="Explain the methodology of the thesis in detail", evidence=[EvidenceReference(document_id="doc_1", chunk_id="c1", text="The methodology uses quantitative analysis.")]))'
)

# Fix test_15: Check input flows instead of retrieval flows (since we moved it to fix the infinite loop)
text = text.replace(
    'assert "retrieval rails" in cfg.rails.retrieval.flows',
    'assert "retrieval rails" in cfg.rails.input.flows'
)

with open("tests/test_nemoguardrails_runtime.py", "w", encoding="utf-8") as f:
    f.write(text)
print("✅ test_10 and test_15 patched.")
