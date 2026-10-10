with open("security/nemoguardrails/runtime.py", "r", encoding="utf-8") as f: text = f.read()
# Add "internal error" to the refusal map to catch action explosions
text = text.replace('("service issue", GuardrailOutcome.ERROR, "fallback_rails"),', '("service issue", GuardrailOutcome.ERROR, "fallback_rails"),\n    ("internal error", GuardrailOutcome.ERROR, "action_error"),')
with open("security/nemoguardrails/runtime.py", "w", encoding="utf-8") as f: f.write(text)
print("✅ runtime.py patched to catch internal errors.")
