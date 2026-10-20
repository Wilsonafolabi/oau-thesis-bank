with open('tests/test_nemoguardrails_runtime.py', 'r', encoding='utf-8') as f:
    text = f.read()
# Replace the literal \n with a real newline
text = text.replace('\\n    assert len(flows)', '\n    assert len(flows)')
with open('tests/test_nemoguardrails_runtime.py', 'w', encoding='utf-8') as f:
    f.write(text)
print("✅ Test file syntax fixed.")
