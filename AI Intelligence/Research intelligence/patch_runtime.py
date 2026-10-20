with open("security/nemoguardrails/runtime.py", "r", encoding="utf-8") as f: text = f.read()
# Remove the context=dict(ctx) argument that is causing the TypeError
text = text.replace(", \n                        context=dict(ctx)", "")
text = text.replace(", context=dict(ctx)", "")
with open("security/nemoguardrails/runtime.py", "w", encoding="utf-8") as f: f.write(text)
print("✅ runtime.py patched to remove context kwarg.")
