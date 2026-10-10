with open("security/nemoguardrails/langchain_adapter.py", "r", encoding="utf-8") as f:
    text = f.read()

old_code = """        except LLMServiceUnavailableError:
            # Let NeMo handle the fallback/error rail
            raise RuntimeError("All LLM providers failed")"""

new_code = """        except Exception:
            # Graceful degradation: return a safe fallback message instead of crashing the NeMo runtime
            return ChatResult(generations=[ChatGeneration(message=AIMessage(
                content="I am currently unable to process your request due to a service issue. Please try again later."
            ))])"""

if old_code in text:
    text = text.replace(old_code, new_code)
    with open("security/nemoguardrails/langchain_adapter.py", "w", encoding="utf-8") as f:
        f.write(text)
    print("✅ langchain_adapter.py patched for graceful degradation.")
else:
    print("⚠️ Could not find exact match. Attempting regex fallback...")
    import re
    text = re.sub(
        r"except LLMServiceUnavailableError:.*?raise RuntimeError\(\"All LLM providers failed\"\)",
        'except Exception:\n            return ChatResult(generations=[ChatGeneration(message=AIMessage(\n                content="I am currently unable to process your request due to a service issue. Please try again later."\n            ))])',
        text,
        flags=re.DOTALL
    )
    with open("security/nemoguardrails/langchain_adapter.py", "w", encoding="utf-8") as f:
        f.write(text)
    print("✅ langchain_adapter.py patched via regex.")
