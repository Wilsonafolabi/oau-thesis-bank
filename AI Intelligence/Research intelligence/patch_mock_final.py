with open("tests/test_nemoguardrails_runtime.py", "r", encoding="utf-8") as f:
    text = f.read()

old_mock = """class MockRouter:
    def complete(self, req):
        class Resp:
            content = "Mocked LLM response about the thesis findings."
            usage = None
            model = "mock"
            provider = "mock"
        return Resp()"""

new_mock = """class MockRouter:
    def complete(self, req):
        class Resp:
            # Smart mock: if NeMo is asking for intent classification, return the correct intent
            prompt_text = req.messages[-1].content.lower() if req.messages else ""
            if "hello" in prompt_text or "canonical" in prompt_text or "express greeting" in prompt_text:
                content = "express greeting"
            else:
                content = "Mocked LLM response about the thesis findings."
            usage = None
            model = "mock"
            provider = "mock"
        return Resp()"""

text = text.replace(old_mock, new_mock)
with open("tests/test_nemoguardrails_runtime.py", "w", encoding="utf-8") as f:
    f.write(text)
print("✅ MockRouter patched to handle intent classification.")
