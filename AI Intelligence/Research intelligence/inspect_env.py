import importlib.util as u
print("paddleocr_available:", bool(u.find_spec("paddleocr")))
print("paddle_available:", bool(u.find_spec("paddle")))
try:
    from transformers import AutoTokenizer
    t = AutoTokenizer.from_pretrained("BAAI/bge-large-en-v1.5")
    print("tokenizer_ok:", t.name_or_path, "vocab_size:", len(t))
except Exception as e:
    print("tokenizer_error:", type(e).__name__, str(e)[:200])
for mod in ("fitz", "pypdf", "docx", "PIL"):
    print(f"{mod}_available:", bool(u.find_spec(mod)))
