with open("tests/test_nemoguardrails_runtime.py", "r", encoding="utf-8") as f: text = f.read()
# Change "Hello" to a complex question to force an LLM call
text = text.replace('user_input="Hello"))\n    assert resp.outcome == GuardrailOutcome.ERROR', 'user_input="Explain the methodology of the thesis in detail"))\n    assert resp.outcome == GuardrailOutcome.ERROR')
with open("tests/test_nemoguardrails_runtime.py", "w", encoding="utf-8") as f: f.write(text)
print("✅ test_10 patched to force LLM call.")
